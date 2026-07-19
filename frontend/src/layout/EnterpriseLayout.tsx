import React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Users, Building2, Settings, Key, Shield,
  Brain, Cpu, Database, Bot, BarChart3, BookOpen, MessageSquare,
  LogOut, Sun, Moon, ChevronRight, FileText, GitBranch
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
  { label: 'AI Workspace', icon: MessageSquare, path: '/workspace', roles: ['ROOT', 'ADMIN', 'USER'] },
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
      { label: 'Models', icon: Cpu, path: '/platform/models', roles: ['ROOT'] },
      { label: 'Prompts', icon: FileText, path: '/platform/prompts', roles: ['ROOT'] },
      { label: 'Agents', icon: Bot, path: '/platform/agents', roles: ['ROOT'] },
      { label: 'Workflows', icon: GitBranch, path: '/platform/workflows', roles: ['ROOT'] },
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
      { label: 'Models', icon: Cpu, path: '/organization/models', roles: ['ROOT', 'ADMIN'] },
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
  const [accountOpen, setAccountOpen] = React.useState(false)
  const accountRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (accountRef.current && !accountRef.current.contains(e.target as Node)) {
        setAccountOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

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
          <div className="relative" ref={accountRef}>
            <button
              onClick={() => setAccountOpen(!accountOpen)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            >
              <div className="w-7 h-7 rounded-full bg-primary-500 flex items-center justify-center text-white text-xs font-bold">
                {user?.username?.[0]?.toUpperCase() || 'U'}
              </div>
              <div className="text-left">
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300 block leading-tight">
                  {user?.username || 'User'}
                </span>
                <span className="text-[10px] text-slate-400 dark:text-slate-500 block leading-tight">
                  {role === 'ROOT' ? 'System Account' : role === 'ADMIN' ? 'Administrator' : 'User'}
                </span>
              </div>
            </button>

            {accountOpen && (
              <div className="absolute right-0 top-full mt-1 w-48 bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 py-1 z-50">
                <div className="px-3 py-2 border-b border-slate-100 dark:border-slate-700 mb-1">
                  <p className="text-sm font-medium text-slate-800 dark:text-white">{user?.username}</p>
                  <p className="text-xs text-slate-400">{role === 'ROOT' ? 'System Account' : role === 'ADMIN' ? 'Administrator' : 'User'}</p>
                </div>
                <button onClick={() => { navigate('/account/profile'); setAccountOpen(false) }} className="w-full text-left px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700">Profile</button>
                <button onClick={() => { navigate('/account/security'); setAccountOpen(false) }} className="w-full text-left px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700">Security</button>
                <button onClick={() => { navigate('/account/api-keys'); setAccountOpen(false) }} className="w-full text-left px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700">API Keys</button>
                <div className="border-t border-slate-100 dark:border-slate-700 mt-1 pt-1">
                  <button onClick={() => { navigate('/account/sessions'); setAccountOpen(false) }} className="w-full text-left px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700">Logout All Devices</button>
                  <button onClick={() => { handleLogout(); setAccountOpen(false) }} className="w-full text-left px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20">Logout</button>
                </div>
              </div>
            )}
          </div>
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

        {/* Content — only children that allow scrolling should scroll */}
        <main className="flex-1 overflow-hidden">
          {children}
        </main>
      </div>
    </div>
  )
}