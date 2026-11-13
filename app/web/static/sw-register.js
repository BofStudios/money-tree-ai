// Service workers only run in a secure context: https, or localhost. Over
  // plain http on the home Wi-Fi the phone still gets a home-screen icon from
  // the manifest; this simply stays quiet instead of throwing.
  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
