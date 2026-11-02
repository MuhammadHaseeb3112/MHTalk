import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { errorMessage } from "../api/client";
import { authApi } from "../api/endpoints";
import { LogoMark } from "../components/common/Icons";
import { Spinner } from "../components/common/ui";
import { navigate } from "../router";
import { normalizePhone } from "../utils/phone";

/** Field-level errors from DRF ({field: [messages]}) */
function fieldErrors(error) {
  const data = error?.response?.data;
  if (!data || typeof data !== "object") return {};
  return Object.fromEntries(
    Object.entries(data).map(([field, value]) => [field, Array.isArray(value) ? value.join(" ") : String(value)]),
  );
}

export default function SignupPage({ onAuthenticated }) {
  const [form, setForm] = useState({ display_name: "", phone: "", email: "", password: "", confirm: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");

  const update = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }));

  function validate() {
    const next = {};
    if (!form.display_name.trim()) next.display_name = "Enter your name.";
    const phone = normalizePhone(form.phone);
    if (!/^\+\d{8,15}$/.test(phone)) next.phone_number = "Enter a valid number with country code, e.g. +92 300 1234567.";
    if (form.email && !/^\S+@\S+\.\S+$/.test(form.email)) next.email = "Enter a valid email address.";
    if (form.password.length < 8) next.password = "Use at least 8 characters.";
    if (form.password !== form.confirm) next.confirm = "Passwords don't match.";
    return next;
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    const local = validate();
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    try {
      const data = await authApi.register({
        display_name: form.display_name.trim(),
        phone_number: normalizePhone(form.phone),
        email: form.email.trim() || undefined,
        password: form.password,
      });
      if (data.access) {
        await onAuthenticated(data);
      } else {
        const login = await authApi.login(normalizePhone(form.phone), form.password);
        await onAuthenticated(login);
      }
    } catch (err) {
      const fields = fieldErrors(err);
      setErrors(fields);
      setError(Object.keys(fields).length ? "" : errorMessage(err, "Couldn't create your account."));
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <div className="auth__brand">
        <LogoMark size={36} />
        <span>MHTalk</span>
      </div>
      <form className="auth__card" onSubmit={submit} noValidate>
        <h1>Create your account</h1>
        <p className="auth__lead">People can find you on MHTalk by this phone number.</p>
        {error ? <div className="form-error" role="alert">{error}</div> : null}

        <div className="field">
          <label htmlFor="su-name">Your name</label>
          <input id="su-name" value={form.display_name} onChange={update("display_name")} autoComplete="name" maxLength={100} autoFocus />
          {errors.display_name ? <span className="field__error">{errors.display_name}</span> : null}
        </div>
        <div className="field">
          <label htmlFor="su-phone">Phone number</label>
          <input id="su-phone" type="tel" placeholder="+92 300 1234567" value={form.phone} onChange={update("phone")} autoComplete="tel" />
          {errors.phone_number ? <span className="field__error">{errors.phone_number}</span> : <span className="field__hint">Local numbers like 0300 1234567 are converted to +92 automatically.</span>}
        </div>
        <div className="field">
          <label htmlFor="su-email">Email (optional)</label>
          <input id="su-email" type="email" value={form.email} onChange={update("email")} autoComplete="email" />
          {errors.email ? <span className="field__error">{errors.email}</span> : null}
        </div>
        <div className="field">
          <label htmlFor="su-password">Password</label>
          <div className="field__password">
            <input id="su-password" type={showPassword ? "text" : "password"} value={form.password} onChange={update("password")} autoComplete="new-password" />
            <button type="button" className="icon-btn" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Hide password" : "Show password"}>
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
          {errors.password ? <span className="field__error">{errors.password}</span> : null}
        </div>
        <div className="field">
          <label htmlFor="su-confirm">Confirm password</label>
          <input id="su-confirm" type={showPassword ? "text" : "password"} value={form.confirm} onChange={update("confirm")} autoComplete="new-password" />
          {errors.confirm ? <span className="field__error">{errors.confirm}</span> : null}
        </div>

        <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
          {busy ? <Spinner size={18} /> : "Create account"}
        </button>
        <p className="auth__switch">
          Already have an account?{" "}
          <a href="/login" onClick={(event) => { event.preventDefault(); navigate("/login"); }}>
            Log in
          </a>
        </p>
      </form>
    </div>
  );
}
