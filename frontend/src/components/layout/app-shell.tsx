import { Outlet } from 'react-router-dom'
import { Nav } from './nav'
import { Sidebar } from './sidebar'

export function AppShell() {
  return (
    <div className="min-h-screen bg-stone-50">
      <Nav />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 pt-14 min-h-screen">
          <div className="p-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
