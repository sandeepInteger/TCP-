function titleCase(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function SetupControls({ setupTypes, setupType, onSetupTypeChange, workAreaWidthFt, onWidthChange }) {
  return (
    <div className="setup-controls">
      <label>
        <span>Setup type</span>
        <select value={setupType} onChange={(e) => onSetupTypeChange(e.target.value)}>
          {setupTypes.map((t) => (
            <option key={t} value={t}>
              {titleCase(t)}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Work area width (ft)</span>
        <input
          type="number"
          min="1"
          step="1"
          value={workAreaWidthFt}
          onChange={(e) => onWidthChange(Number(e.target.value))}
        />
      </label>
      <p className="setup-controls-hint">
        Applied to every detected speed-limit sign below to calculate buffer, taper, sign, and cone spacing.
      </p>
    </div>
  );
}
