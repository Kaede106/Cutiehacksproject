// Camera lifecycle: feature detection, opening a stream, mapping errors, stopping tracks.

/** Returns { ok, reason } where reason is 'insecure' or 'unsupported' when the camera can't be used. */
export function getCameraSupport() {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return { ok: false, reason: 'unsupported' };
  if (!window.isSecureContext) return { ok: false, reason: 'insecure' };
  if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== 'function') {
    return { ok: false, reason: 'unsupported' };
  }
  return { ok: true, reason: null };
}

/** 'granted' | 'denied' | 'prompt' | 'unknown'. Some browsers can't query the camera permission. */
export async function queryCameraPermission() {
  try {
    const status = await navigator.permissions.query({ name: 'camera' });
    return status.state;
  } catch {
    return 'unknown';
  }
}

export function openCamera() {
  return navigator.mediaDevices.getUserMedia({
    audio: false,
    video: {
      // Prefer the rear camera on phones; laptops only have the front one.
      facingMode: { ideal: 'environment' },
      width: { ideal: 960 },
      height: { ideal: 720 },
    },
  });
}

/** Map a getUserMedia error to a scanner state. */
export function describeCameraError(err) {
  switch (err && err.name) {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
      return 'denied';
    case 'SecurityError':
      return 'blocked';
    case 'NotSupportedError':
      return 'unsupported';
    case 'NotFoundError':
    case 'DevicesNotFoundError':
    case 'OverconstrainedError':
      return 'notfound';
    case 'NotReadableError':
    case 'TrackStartError':
    case 'AbortError':
      return 'busy';
    default:
      return 'error';
  }
}

export function stopStream(stream) {
  if (!stream) return;
  for (const track of stream.getTracks()) track.stop();
}
