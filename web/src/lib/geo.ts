import type { FeatureCollection, Geometry } from 'geojson'

export type DistrictFC = FeatureCollection<Geometry, { lgd: number; district: string; state: string }>

// Kicked off at module load (main.tsx imports this) so the geometry downloads in parallel with /api/districts.
const j = <T,>(u: string) => fetch(u).then((r) => { if (!r.ok) throw new Error(`${u}: ${r.status}`); return r.json() as Promise<T> })
export const geoPromise: Promise<DistrictFC> = j<DistrictFC>('/districts.geojson')
export const statesPromise: Promise<FeatureCollection> = j<FeatureCollection>('/states.geojson')
geoPromise.catch(() => undefined)
statesPromise.catch(() => undefined)
