// Bridge to the shell's action tracker, exposed as window.annadrishtiTracker. Accessed through a cast so this file
// does not clash with a global declaration made elsewhere.
export interface TrackerApi {
  add: (a: { lgd: number; action: string; dept: string; due: string | null }) => void
  has?: (lgd: number, action: string) => boolean
}
export const trackerApi = (): TrackerApi | undefined => (typeof window === 'undefined' ? undefined : (window as unknown as { annadrishtiTracker?: TrackerApi }).annadrishtiTracker)
