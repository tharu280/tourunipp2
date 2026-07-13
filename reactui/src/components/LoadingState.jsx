export default function LoadingState({ title, detail, steps = [] }) {
  return (
    <main className="loading-screen" id="screen-loading">
      <div className="loading-spinner-wrap">
        <div className="loading-spinner" role="status" aria-label="Loading" />
      </div>
      <h1 className="loading-title">{title}</h1>
      <p className="loading-detail">{detail}</p>
      {steps.length > 0 && (
        <div className="loading-progress" aria-hidden="true"><span /></div>
      )}
      {steps.length > 0 && (
        <ol className="loading-steps" aria-label="Planning progress">
          {steps.map((step, i) => (
            <li key={i} className="loading-step"><span>{i + 1}</span>{step}</li>
          ))}
        </ol>
      )}
    </main>
  );
}
