import { memo } from 'react';

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export const Toggle = memo(function Toggle({ checked, onChange, disabled }: ToggleProps) {
  return (
    <button
      type="button"
      className={`toggle ${checked ? 'toggle-on' : 'toggle-off'} ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
    >
      <span className="toggle-dot" />
    </button>
  );
});
