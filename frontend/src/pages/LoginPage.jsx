import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { errorMessage } from "../api/client";
import { authApi } from "../api/endpoints";
import { LogoMark } from "../components/common/Icons";
import { Spinner } from "../components/common/ui";
import { navigate } from "../router";
import { normalizePhone } from "../utils/phone";

export default function LoginPage({ onAuthenticated }) {
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!phone.trim() || !password) {
      setError("Enter your phone number and password.");
      return;
    }
    setBusy(true);
    try {
      const data = await authApi.login(normalizePhone(phone), password);
      await onAuthenticated(data);
    } catch (err) {
      setError(errorMessage(err, "Couldn't sign in."));
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
        <h1>Log in to MHTalk</h1>
        <p className="auth__lead">Use the phone number and password of your MHTalk account.</p>
        {error ? <div className="form-error" role="alert">{error}</div> : null}
        <div className="field">
          <label htmlFor="login-phone">Phone number</label>
          <input
            id="login-phone"
            type="tel"
            autoComplete="tel"
            placeholder="+92 300 1234567"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            autoFocus
          />
        </div>
        <div className="field">
          <label htmlFor="login-password">Password</label>
          <div className="field__password">
            <input
              id="login-password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <button type="button" className="icon-btn" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Hide password" : "Show password"}>
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
        </div>
        <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
          {busy ? <Spinner size={18} /> : "Log in"}
        </button>
        <p className="auth__switch">
          New to MHTalk?{" "}
          <a href="/signup" onClick={(event) => { event.preventDefault(); navigate("/signup"); }}>
            Create an account
          </a>
        </p>
      </form>
      <p className="auth__foot">Your messages sync in real time across all your open tabs and devices.</p>
    </div>
  );
}
