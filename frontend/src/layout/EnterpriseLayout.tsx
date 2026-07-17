import React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Users, Building2, Settings, Key, Shield,
  Brain, Cpu, Database, Bot, BarChart3, BookOpen, MessageSquare,
  LogOut, Sun, Moon, ChevronRight
} from 'lucide-react'
import { useAuthStore } from '../store/auth'
import { usePermission } from '../hooks/usePermission'
import { useThemeStore } from '../contexts/ThemeContext'

interface NavItem {
  label: string
  icon: React.ElementType
  path: string
  roles: ('ROOT' | 'ADMIN' | 'USER')[]
  children?: NavItem[]
}

const NAV_ITEMS: NavItem[] = [
  { label: 'AI Chat', icon: MessageSquare, path: '/', roles: ['ROOT', 'ADMIN', 'USER'] },
  {
    label: 'Admin Center',
    icon: Shield,
    path: '/admin',
    roles: ['ROOT'],
    children: [
      { label: 'Dashboard', icon: LayoutDashboard, path: '/admin', roles: ['ROOT'] },
      { label: 'Users', icon: Users, path: '/admin/users', roles: ['ROOT'] },
      { label: 'System Config', icon: Settings, path: '/admin/system', roles: ['ROOT'] },
      { label: 'API Keys', icon: Key, path: '/admin/api-keys', roles: ['ROOT'] },
      { label: 'Audit Logs', icon: BarChart3, path: '/admin/audit', roles: ['ROOT'] },
    ],
  },
  {
    label: 'Organization',
    icon: Building2,
    path: '/organization',
    roles: ['ROOT', 'ADMIN'],
    children: [
      { label: 'Overview', icon: Building2, path: '/organization', roles: ['ROOT', 'ADMIN'] },
      { label: 'Members', icon: Users, path: '/organization/members', roles: ['ROOT', 'ADMIN'] },
      { label: 'Departments', icon: Building2, path: '/organization/departments', roles: ['ROOT', 'ADMIN'] },
    ],
  },
  { label: 'Knowledge ACL', icon: BookOpen, path: '/knowledge/acl', roles: ['ROOT', 'ADMIN'] },
  { label: 'Quota', icon: BarChart3, path: '/quota', roles: ['ROOT', 'ADMIN'] },
  {
    label: 'AI Console',
    icon: Brain,
    path: '/ai/models',
    roles: ['ROOT', 'ADMIN', 'USER'],
    children: [
      { label: 'Models', icon: Cpu, path: '/ai/models', roles: ['ROOT', 'ADMIN', 'USER'] },
      { label: 'Embedding', icon: Database, path: '/ai/embedding', roles: ['ROOT', 'ADMIN', 'USER'] },
      { label: 'Retrieval', icon: Bot, path: '/ai/retrieval', roles: ['ROOT', 'ADMIN', 'USER'] },
      { label: 'Agent', icon: Bot, path: '/ai/agent', roles: ['ROOT', 'ADMIN', 'USER'] },
    ],
  },
  { label: 'Monitoring', icon: BarChart3, path: '/monitoring', roles: ['ROOT'] },
]

export default function EnterpriseLayout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const { role, isRoot, isAdmin } = usePermission()
  const { theme, toggleTheme } = useThemeStore()
  const [sidebarOpen, setSidebarOpen] = React.useState(true)
  const [expandedMenus, setExpandedMenus] = React.useState<string[]>(['Admin Center', 'AI Console'])

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const canSee = (item: NavItem) => {
    return item.roles.includes(role)
  }

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/'
    return location.pathname.startsWith(path)
  }

  const toggleMenu = (label: string) => {
    setExpandedMenus(prev =>
      prev.includes(label) ? prev.filter(l => l !== label) : [...prev, label]
    )
  }

  const filteredNav = NAV_ITEMS.filter(canSee)

  return (
    <div className="h-screen flex flex-col bg-slate-50 dark:bg-slate-900">
      {/* Top Bar */}
      <header className="h-14 flex-shrink-0 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 flex items-center px-4 z-50">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 mr-3"
        >
          <ChevronRight className={`w-5 h-5 text-slate-500 transition-transform ${sidebarOpen ? 'rotate-180' : ''}`} />
        </button>

        <div className="flex items-center gap-2">
          <Brain className="w-6 h-6 text-primary-500" />
          <span className="font-bold text-slate-800 dark:text-slate-100">Knowledge Chat</span>
          {role && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300 font-medium">
              {role}
            </span>
          )}
        </div>

        <div className="flex-1" />

        <div className="flex items-center gap-2">
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500"
          >
            {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
          <div className="flex items-center gap-2 px-3 py-1.5">
            <div className="w-7 h-7 rounded-full bg-primary-500 flex items-center justify-center text-white text-xs font-bold">
              {user?.username?.[0]?.toUpperCase() || 'U'}
            </div>
            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
              {user?.username || 'User'}
            </span>
          </div>
          <button
            onClick={handleLogout}
            className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-slate-400 hover:text-red-500"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside
          className={`flex-shrink-0 bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 
                      transition-all duration-300 overflow-hidden ${
            sidebarOpen ? 'w-56' : 'w-0'
          }`}
        >
          <div className="w-56 h-full overflow-y-auto py-2">
            {filteredNav.map((item) => {
              if (item.children) {
                const isExpanded = expandedMenus.includes(item.label)
                const hasActiveChild = item.children.some(c => isActive(c.path))
                return (
                  <div key={item.label}>
                    <button
                      onClick={() => toggleMenu(item.label)}
                      className={`w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg mx-2
                                 ${hasActiveChild
                                   ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/20 dark:text-primary-300'
                                   : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                                 }`}
                    >
                      <item.icon className="w-4 h-4 flex-shrink-0" />
                      <span className="flex-1 text-left">{item.label}</span>
                      <ChevronRight className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                    </button>
                    {isExpanded && (
                      <div className="ml-4 mt-1 space-y-0.5">
                        {item.children.filter(canSee).map((child) => (
                          <button
                            key={child.path}
                            onClick={() => navigate(child.path)}
                            className={`w-full flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg
                                       ${isActive(child.path)
                                         ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/20 dark:text-primary-300 font-medium'
                                         : 'text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700'
                                       }`}
                          >
                            <child.icon className="w-3.5 h-3.5" />
                            {child.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )
              }
              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg mx-2 my-0.5
                             ${isActive(item.path)
                               ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/20 dark:text-primary-300 font-medium'
                               : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                             }`}
                >
                  <item.icon className="w-4 h-4" />
                  {item.label}
                </button>
              )
            })}
          </div>
        </aside>

        {/* Content */}
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  )
}