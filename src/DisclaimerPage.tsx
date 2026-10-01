export function DisclaimerPage({ navigate }: { navigate: (path: string) => void }) {
  return <main className="disclaimer-page">
    <button className="text-button back-link" onClick={() => navigate('/')}>← Back to redacting</button>
    <h1>Disclaimer</h1>
    <p className="information-lead">Redacted can help remove sensitive text. It does not guarantee that a document is safe to share.</p>
    <section>
      <h2>Review every output</h2>
      <p>The model can miss sensitive information or flag ordinary text. Sensitivity is a detection setting, not an accuracy or confidence score. Check the entire exported document before relying on it or sharing it.</p>
    </section>
    <section>
      <h2>Document limits</h2>
      <p>Images are not scanned for sensitive information, and this app does not perform OCR. Scanned documents need separate OCR before processing. Preserved images and other content can still reveal private information. Check the scan report for warnings and limitations.</p>
      <p>Formatting may change. If the original layout cannot be preserved, the app can produce a clean text rewrite. Synthetic replacements are fictional and should not be treated as factual information.</p>
    </section>
    <section>
      <h2>Processing and privacy</h2>
      <p>The local server can see document contents while processing them. Guest filenames and detected original values remain in temporary memory; generated guest files are temporary too. Hiding a value behind a black bar in the interface is not encryption.</p>
      <p>Deleting a result does not remove files you have downloaded, backups or copies outside the app. Review those copies and handle them appropriately.</p>
    </section>
    <section>
      <h2>No guarantees</h2>
      <p>No guarantee is made about detection accuracy, complete redaction, anonymity, output correctness or suitability for a particular purpose. You are responsible for deciding whether an output is appropriate to use or share. Redacted does not certify compliance with confidentiality or data-protection requirements.</p>
    </section>
  </main>;
}
