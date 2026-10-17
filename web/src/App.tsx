import { useEffect, useState } from 'react'
import { Spinner } from './components/ui'
import { bootstrap } from './lib/api'
import { useStore } from './lib/store'
import { navigate, useRoute } from './lib/route'
import Header from './components/Header'
import RolePicker from './components/RolePicker'
import ChatPanel from './components/ChatPanel'
import Footer from './components/Footer'
import MethodsModal from './components/MethodsModal'
import FarmerRoute from './routes/FarmerRoute'
import OfficerRoute from './routes/OfficerRoute'
import PlannerRoute from './routes/PlannerRoute'

export default function App() {
  const { loading, error, setData, setError, role, setRole, mode, setMode } = useStore()
  const route = useRoute()
  const [methods, setMethods] = useState(false)
  const [picker, setPicker] = useState(false)
  useEffect(() => {
    bootstrap().then((b) => setData(b.districts, b.kpis, b.mock)).catch((e: Error) => setError(e.message))
  }, [setData, setError])

  // the URL is the source of truth for the role; "/" redirects to the remembered role (or asks)
  useEffect(() => {
    if (route === 'root') { if (role) navigate(role, true) } else if (route !== role) setRole(route)
  }, [route, role, setRole])
  useEffect(() => {
    document.documentElement.classList.toggle('farmer', route === 'farmer')
    if (route === 'farmer' && mode === 'history') setMode('now')
  }, [route, mode, setMode])

  const first = route === 'root' && !role
  return (
    <div className="flex h-[100dvh] flex-col bg-surface">
      <Header onMethods={() => setMethods(true)} />
      {loading ? (
        <div className="grid flex-1 place-items-center"><Spinner label="Loading district data…" /></div>
      ) : error ? (
        <div className="grid flex-1 place-items-center p-8 text-center md-body-large text-act-ink">Could not load data: {error}</div>
      ) : (
        <>
          {route === 'farmer' && <FarmerRoute />}
          {route === 'officer' && <OfficerRoute />}
          {route === 'planner' && <PlannerRoute />}
          {route !== 'root' && <ChatPanel />}
        </>
      )}
      {route !== 'farmer' && <Footer onMethods={() => setMethods(true)} />}
      <RolePicker open={first || picker} onClose={() => setPicker(false)} dismissible={!first} />
      {methods && <MethodsModal onClose={() => setMethods(false)} />}
    </div>
  )
}
