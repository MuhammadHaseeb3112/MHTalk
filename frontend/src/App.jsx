import { useCallback, useEffect, useState } from "react";
import { onSessionExpired, tokens } from "./api/client";
import { authApi } from "./api/endpoints";
import { Spinner, ToastHost } from "./components/common/ui";
import DialogHost from "./components/common/DialogHost";
import { LogoMark } from "./components/common/Icons";
import JoinGroupDialog from "./components/join/JoinGroupDialog";
import MainLayout from "./components/layout/MainLayout";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";
import { navigate, usePathname } from "./router";
import { realtime } from "./services/realtime";
import { forgetBackgroundPushOnLogout, syncBackgroundPush } from "./services/push";
import { bootstrap } from "./store/actions";
import { dispatch, useStore } from "./store/store";

const AFTER_LOGIN_KEY = "whatsup:after-login";
const JOIN_PATTERN = /^\/join\/([A-Za-z0-9_-]{1,64})$/;

/** Where to go after signing in (e.g. back to a /join/<code> link). */
function takeAfterLogin() {
  try {
    const path = sessionStorage.getItem(AFTER_LOGIN_KEY);
    sessionStorage.removeItem(AFTER_LOGIN_KEY);
    return path && JOIN_PATTERN.test(path) ? path : "/";
  } catch {
    return "/";
  }
}

/**
 * Auth gate + routing.
 *   /login        sign in
 *   /signup       create an account
 *   /join/<code>  group invite link (signed out: log in first, then come back)
 *   /             the app (protected)
 */
export default function App() {
  const path = usePathname();
  const joinCode = JOIN_PATTERN.exec(path)?.[1] || null;
  const me = useStore((state) => state.me);
  const [checking, setChecking] = useState(Boolean(tokens.access || tokens.refresh));

  const signOutLocally = useCallback(() => {
    realtime.stop();
    tokens.clear();
    dispatch({ type: "reset" });
    navigate("/login", { replace: true });
  }, []);

  const startSession = useCallback(async (user) => {
    dispatch({ type: "me", me: user });
    realtime.start({ onSessionExpired: signOutLocally });
    syncBackgroundPush();
    await bootstrap();
  }, [signOutLocally]);

  // Restore an existing session on load.
  useEffect(() => {
    let cancelled = false;
    if (!tokens.access && !tokens.refresh) return undefined;
    authApi
      .me()
      .then((user) => {
        if (!cancelled) return startSession(user);
        return null;
      })
      .catch(() => {
        if (!cancelled) signOutLocally();
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [startSession, signOutLocally]);

  useEffect(() => onSessionExpired(signOutLocally), [signOutLocally]);

  // Account deleted (this tab or another one): back to the login page.
  useEffect(() => {
    window.addEventListener("whatsup:signed-out", signOutLocally);
    return () => window.removeEventListener("whatsup:signed-out", signOutLocally);
  }, [signOutLocally]);

  // Keep "me" fresh when the profile changes in another tab/device.
  useEffect(() => {
    const reload = () => authApi.me().then((user) => dispatch({ type: "me", me: user })).catch(() => {});
    window.addEventListener("whatsup:me-changed", reload);
    return () => window.removeEventListener("whatsup:me-changed", reload);
  }, []);

  // Route guards.
  useEffect(() => {
    if (checking) return;
    const isAuthRoute = path === "/login" || path === "/signup";
    if (!me && !isAuthRoute) {
      if (JOIN_PATTERN.test(path)) {
        try {
          sessionStorage.setItem(AFTER_LOGIN_KEY, path);
        } catch {
          /* storage unavailable */
        }
      }
      navigate("/login", { replace: true });
    }
    if (me && isAuthRoute) navigate(takeAfterLogin(), { replace: true });
  }, [checking, me, path]);

  const handleAuthenticated = useCallback(
    async ({ access, refresh, user }) => {
      tokens.set({ access, refresh });
      await startSession(user);
      // The route guard may already have moved on (e.g. back to /join/<code>).
      if (["/login", "/signup"].includes(window.location.pathname)) navigate(takeAfterLogin(), { replace: true });
    },
    [startSession],
  );

  const handleLogout = useCallback(async () => {
    await forgetBackgroundPushOnLogout();
    try {
      if (tokens.refresh) await authApi.logout(tokens.refresh);
    } catch {
      /* the token may already be invalid */
    }
    signOutLocally();
  }, [signOutLocally]);

  let content;
  if (checking) {
    content = (
      <div className="splash">
        <LogoMark size={64} />
        <Spinner size={28} />
        <p>Loading your chats…</p>
      </div>
    );
  } else if (!me) {
    content = path === "/signup" ? <SignupPage onAuthenticated={handleAuthenticated} /> : <LoginPage onAuthenticated={handleAuthenticated} />;
  } else {
    content = (
      <>
        <MainLayout onLogout={handleLogout} />
        {joinCode ? <JoinGroupDialog key={joinCode} code={joinCode} /> : null}
      </>
    );
  }

  return (
    <>
      {content}
      <DialogHost />
      <ToastHost />
    </>
  );
}
