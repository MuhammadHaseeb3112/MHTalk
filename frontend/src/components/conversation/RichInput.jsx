import { useImperativeHandle, useLayoutEffect, useRef } from "react";

/*
 * A one-field text box built on contentEditable instead of <textarea>.
 *
 * Why: phone keyboards (Gboard, Samsung) can only insert GIFs, stickers and
 * pictures into rich-text fields. On a <textarea> Chrome shows "This app does
 * not support GIFs here". Here the picture arrives as a file (onFiles) and
 * everything else behaves like a plain textarea: the parent passes
 * value/onChange and gets selectionStart / setSelectionRange / focus on
 * the ref, so existing textarea code keeps working.
 */

/** Plain text of a node tree: text, <br> → "\n", blocks start a new line. */
function serialize(root) {
  let out = "";
  const walk = (node) => {
    node.childNodes.forEach((child) => {
      if (child.nodeType === Node.TEXT_NODE) out += child.data;
      else if (child.nodeName === "BR") out += "\n";
      else if (child.nodeName === "IMG") out += "";
      else {
        const block = /^(DIV|P|LI)$/.test(child.nodeName);
        if (block && out && !out.endsWith("\n")) out += "\n";
        walk(child);
      }
    });
  };
  walk(root);
  return out;
}

function textOf(el) {
  let text = serialize(el);
  // Chrome keeps a trailing <br> so the caret can sit on an empty last line.
  if (el.lastChild?.nodeName === "BR" && text.endsWith("\n")) text = text.slice(0, -1);
  return text.replace(/\u00a0/g, " ");
}

function caretOffset(el, atEnd) {
  const selection = window.getSelection();
  if (!selection?.rangeCount) return null;
  const range = selection.getRangeAt(0);
  if (!el.contains(range.startContainer)) return null;
  const before = document.createRange();
  before.selectNodeContents(el);
  before.setEnd(atEnd ? range.endContainer : range.startContainer, atEnd ? range.endOffset : range.startOffset);
  const holder = document.createElement("div");
  holder.appendChild(before.cloneContents());
  return serialize(holder).length;
}

function placeCaret(el, start, end = start) {
  const find = (target) => {
    let left = target;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let node = walker.nextNode();
    while (node) {
      if (node.nodeType === Node.TEXT_NODE) {
        if (left <= node.data.length) return [node, left];
        left -= node.data.length;
      } else if (node.nodeName === "BR") {
        if (left === 0) return [node.parentNode, Array.prototype.indexOf.call(node.parentNode.childNodes, node)];
        left -= 1;
      }
      node = walker.nextNode();
    }
    return [el, el.childNodes.length];
  };
  const [startNode, startOffset] = find(start);
  const [endNode, endOffset] = find(end);
  const range = document.createRange();
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

function render(el, value) {
  el.textContent = "";
  const lines = value.split("\n");
  lines.forEach((line, index) => {
    if (index) el.appendChild(document.createElement("br"));
    if (line) el.appendChild(document.createTextNode(line));
  });
  if (value.endsWith("\n")) el.appendChild(document.createElement("br"));
}

async function filesFromImages(el) {
  const images = [...el.querySelectorAll("img")];
  const files = [];
  for (const img of images) {
    const src = img.getAttribute("src") || "";
    img.remove();
    try {
      const blob = await (await fetch(src)).blob();
      if (blob.size) {
        const ext = (blob.type.split("/")[1] || "png").replace("jpeg", "jpg");
        files.push(new File([blob], `keyboard-${Date.now()}.${ext}`, { type: blob.type || "image/png" }));
      }
    } catch {
      /* the keyboard gave a link we can't read */
    }
  }
  return files;
}

export default function RichInput({ ref, value, onChange, onKeyDown, onFiles, onBlur, placeholder, maxLength = 65000, disabled = false, className = "", ...rest }) {
  const elRef = useRef(null);

  useImperativeHandle(
    ref,
    () => ({
      get value() {
        return elRef.current ? textOf(elRef.current) : "";
      },
      get selectionStart() {
        return elRef.current ? (caretOffset(elRef.current, false) ?? textOf(elRef.current).length) : 0;
      },
      get selectionEnd() {
        return elRef.current ? (caretOffset(elRef.current, true) ?? textOf(elRef.current).length) : 0;
      },
      setSelectionRange(start, end) {
        if (elRef.current && document.activeElement === elRef.current) placeCaret(elRef.current, start, end);
      },
      focus() {
        const el = elRef.current;
        if (!el) return;
        el.focus({ preventScroll: true });
        if (caretOffset(el, false) === null) placeCaret(el, textOf(el).length);
      },
      blur() {
        elRef.current?.blur();
      },
      // The textarea auto-grow code sets style.height; CSS handles it here.
      style: {},
      scrollHeight: 0,
    }),
    [],
  );

  // Keep the DOM in step when the parent changes the text (send, emoji, mention).
  useLayoutEffect(() => {
    const el = elRef.current;
    if (!el || textOf(el) === value) return;
    const focused = document.activeElement === el;
    render(el, value);
    if (focused) placeCaret(el, value.length);
  }, [value]);

  // Native beforeinput: keyboard pictures (dataTransfer) and Enter from
  // phone keyboards ("insertParagraph") which would otherwise add a <div>.
  const handlers = useRef({});
  useLayoutEffect(() => {
    handlers.current = { takeFiles, emit };
  });
  useLayoutEffect(() => {
    const el = elRef.current;
    const onBeforeInput = (event) => {
      if (event.dataTransfer && handlers.current.takeFiles(event.dataTransfer)) {
        event.preventDefault();
        return;
      }
      if (event.inputType === "insertParagraph") {
        event.preventDefault();
        document.execCommand("insertLineBreak");
        handlers.current.emit();
      }
    };
    el.addEventListener("beforeinput", onBeforeInput);
    return () => el.removeEventListener("beforeinput", onBeforeInput);
  }, []);

  function emit() {
    const el = elRef.current;
    let text = textOf(el);
    if (text.length > maxLength) {
      text = text.slice(0, maxLength);
      render(el, text);
      placeCaret(el, text.length);
    }
    onChange?.({ target: { value: text, selectionStart: caretOffset(el, false) ?? text.length } });
  }

  function insertPlain(text) {
    // execCommand keeps the browser's undo history and caret handling.
    if (!document.execCommand("insertText", false, text)) {
      const selection = window.getSelection();
      if (!selection?.rangeCount) return;
      const range = selection.getRangeAt(0);
      range.deleteContents();
      range.insertNode(document.createTextNode(text));
      range.collapse(false);
    }
  }

  function takeFiles(dataTransfer) {
    const files = [...(dataTransfer?.files || [])].filter((file) => /^(image|video)\//.test(file.type));
    if (files.length) onFiles?.(files);
    return files.length > 0;
  }

  return (
    <div
      {...rest}
      ref={elRef}
      className={`${className} rich-input ${value ? "" : "is-empty"}`}
      contentEditable={!disabled}
      aria-disabled={disabled || undefined}
      suppressContentEditableWarning
      role="textbox"
      aria-multiline="true"
      data-placeholder={placeholder}
      spellCheck
      onInput={async () => {
        const el = elRef.current;
        if (el.querySelector("img")) {
          // A keyboard GIF / sticker / picture landed inside the text box.
          const files = await filesFromImages(el);
          if (files.length) onFiles?.(files);
        }
        emit();
      }}
      onPaste={(event) => {
        event.preventDefault();
        if (takeFiles(event.clipboardData)) return;
        const text = event.clipboardData?.getData("text/plain") || "";
        if (text) insertPlain(text);
      }}
      onDrop={(event) => {
        if (takeFiles(event.dataTransfer)) event.preventDefault();
      }}
      onKeyDown={(event) => {
        onKeyDown?.(event);
        if (event.defaultPrevented) return;
        if (event.key === "Enter" && !event.nativeEvent.isComposing) {
          // New line as <br>, never a <div> block.
          event.preventDefault();
          document.execCommand("insertLineBreak");
          emit();
        }
      }}
      onBlur={onBlur}
    />
  );
}
