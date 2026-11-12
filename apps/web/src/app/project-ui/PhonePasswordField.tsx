"use client";

import { useId, useState } from "react";
import { PHONE_PASSWORD_MAX_LENGTH } from "@/lib/phone-password-validation";

type Props = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  autoComplete: "current-password" | "new-password";
  disabled: boolean;
  shown: boolean;
  onToggle: () => void;
  visibilityLabel: string;
  error: string;
  validate: boolean;
};

export function PhonePasswordField(props: Props) {
  const [touched, setTouched] = useState(false);
  const errorId = useId();
  const showError = Boolean(props.error && (touched || props.validate || props.value.length > PHONE_PASSWORD_MAX_LENGTH || /\s/.test(props.value)));
  return <div className="phone-password-field">
    <label className={`password-input-row ${props.value ? "filled" : ""} ${showError ? "password-input-invalid" : ""}`}>
      <input aria-label={props.label} disabled={props.disabled} value={props.value}
        onChange={event => {
          const value = event.target.value;
          if (value.length > PHONE_PASSWORD_MAX_LENGTH || /\s/.test(value)) setTouched(true);
          props.onChange(value);
        }} onBlur={() => setTouched(true)}
        placeholder={props.placeholder} type={props.shown ? "text" : "password"} autoComplete={props.autoComplete}
        aria-invalid={showError} aria-describedby={showError ? errorId : undefined} />
      <button type="button" className="password-visibility" aria-label={`${props.shown ? "隐藏" : "显示"}${props.visibilityLabel}`}
        aria-pressed={props.shown} onClick={props.onToggle}>{props.shown ? "隐藏" : "显示"}</button>
    </label>
    {showError && <p id={errorId} className="phone-password-error" role="alert">{props.error}</p>}
  </div>;
}
