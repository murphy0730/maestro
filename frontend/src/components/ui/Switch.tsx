/**
 * Switch — a real `role="switch"`, not a styled div. Keyboard-operable and
 * announced with its checked state. Label it via `aria-label`, or point
 * `aria-labelledby` at the visible row title.
 */
interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  'aria-label'?: string;
  'aria-labelledby'?: string;
  'aria-describedby'?: string;
}

export function Switch({ checked, onChange, disabled = false, ...aria }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-5 w-[34px] flex-none rounded-pill border transition-colors duration-fast ease-out ${
        checked ? 'border-transparent bg-blue-solid' : 'border-border-default bg-surface-3'
      } ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
      {...aria}
    >
      <span
        aria-hidden="true"
        className={`absolute top-[2px] h-[14px] w-[14px] rounded-full transition-all duration-fast ease-out ${
          checked ? 'left-[16px] bg-on-solid' : 'left-[2px] bg-text-tertiary'
        }`}
      />
    </button>
  );
}
