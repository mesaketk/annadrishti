export default function Footer({ onMethods }: { onMethods: () => void }) {
  return (
    <footer className="hidden shrink-0 border-t border-outline-variant bg-surface-container px-4 py-2 md-body-small text-muted md:block">
      These are scenarios built from past years, not exact forecasts.{' '}
      <button onClick={onMethods} className="font-medium text-primary underline underline-offset-2">Data &amp; methods</button>
      <span className="hidden md:inline"> · Sources: IMD rainfall, NOAA ENSO, agriculture production statistics, national health surveys, Census 2011, FCI stocks, satellite data.</span>
    </footer>
  )
}
