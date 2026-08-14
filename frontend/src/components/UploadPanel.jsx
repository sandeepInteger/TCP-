import { useCallback, useRef, useState } from "react";

const ACCEPTED_EXTENSIONS = [".kml", ".kmz"];

function isAccepted(file) {
  const lower = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FileIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path
        d="M6 3h7l5 5v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M13 3v5h5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

export default function UploadPanel({ onFileSelected, loading, ready, onContinue }) {
  const [dragActive, setDragActive] = useState(false);
  const [localError, setLocalError] = useState(null);
  const [activeFile, setActiveFile] = useState(null);
  const inputRef = useRef(null);

  const handleFile = useCallback(
    (file) => {
      if (!file) return;
      if (!isAccepted(file)) {
        setLocalError(`"${file.name}" is not a .kml or .kmz file.`);
        setActiveFile(null);
        return;
      }
      setLocalError(null);
      setActiveFile(file);
      onFileSelected(file);
    },
    [onFileSelected]
  );

  return (
    <div className="upload-card">
      <div className="upload-card-header">
        <h1>Upload your new work</h1>
        <p className="upload-card-subtitle">Add a KML or KMZ file to generate your TCP drawing</p>
      </div>

      <div
        className={`upload-panel ${dragActive ? "drag-active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          handleFile(e.dataTransfer.files?.[0]);
        }}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".kml,.kmz"
          hidden
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        <div className="upload-icon-badge">
          <svg className="upload-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M12 15V4M12 4L8 8M12 4L16 8M5 16v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <p className="upload-title">Drag &amp; drop your file here, or choose file</p>
        <p className="upload-hint">Accepted formats: .kml, .kmz</p>
        {localError && <p className="upload-error">{localError}</p>}
      </div>

      {activeFile && loading && (
        <div className="upload-file-row">
          <span className="upload-file-icon" aria-hidden="true">
            <FileIcon />
          </span>
          <span className="upload-file-info">
            <span className="upload-file-name">{activeFile.name}</span>
            <span className="upload-file-size">{formatBytes(activeFile.size)} · Processing…</span>
          </span>
          <span className="upload-file-spinner" aria-label="Processing" />
        </div>
      )}

      {activeFile && ready && !loading && (
        <>
          <div className="upload-file-row upload-file-row-ready">
            <span className="upload-file-icon upload-file-icon-success" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="9.5" stroke="currentColor" strokeWidth="1.6" />
                <path d="M8 12.2l2.6 2.6L16.2 9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <span className="upload-file-info">
              <span className="upload-file-name">{activeFile.name}</span>
              <span className="upload-file-size">{formatBytes(activeFile.size)} · Ready</span>
            </span>
          </div>
          <button type="button" className="btn-primary upload-continue-btn" onClick={onContinue}>
            Continue
          </button>
        </>
      )}
    </div>
  );
}
