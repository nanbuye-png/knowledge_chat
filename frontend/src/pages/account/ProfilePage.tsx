import { User, Shield, Calendar, BadgeCheck } from 'lucide-react'
import { useAuthStore } from '../../store/auth'
import { usePermission } from '../../hooks/usePermission'

export default function ProfilePage() {
  const user = useAuthStore((s) => s.user)
  const { role, isSystemAccount } = usePermission()

  const roleLabel = isSystemAccount() ? 'System Account' : role === 'ADMIN' ? 'Administrator' : role === 'ROOT' ? 'System Account' : 'User'

  return (
    <div className="p-8 max-w-2xl">
      <h2 className="text-xl font-bold text-slate-800 dark:text-white mb-6 flex items-center gap-2">
        <User className="w-5 h-5 text-primary-500" />
        Profile
      </h2>

      <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 overflow-hidden">
        {/* Avatar */}
        <div className="p-6 flex items-center gap-4 border-b border-slate-100 dark:border-slate-700">
          <div className="w-14 h-14 rounded-full bg-primary-500 flex items-center justify-center text-white text-xl font-bold">
            {user?.username?.[0]?.toUpperCase() || 'U'}
          </div>
          <div>
            <p className="text-lg font-semibold text-slate-800 dark:text-white">{user?.username}</p>
            <p className="text-sm text-slate-500 dark:text-slate-400">{roleLabel}</p>
          </div>
        </div>

        {/* Details */}
        <div className="p-6 space-y-4">
          <div className="flex items-center gap-3">
            <User className="w-4 h-4 text-slate-400" />
            <span className="text-sm text-slate-500 w-24">Username</span>
            <span className="text-sm text-slate-800 dark:text-slate-200">{user?.username}</span>
          </div>
          <div className="flex items-center gap-3">
            <Shield className="w-4 h-4 text-slate-400" />
            <span className="text-sm text-slate-500 w-24">Role</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300">
              {roleLabel}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <Calendar className="w-4 h-4 text-slate-400" />
            <span className="text-sm text-slate-500 w-24">Created</span>
            <span className="text-sm text-slate-800 dark:text-slate-200">
              {user?.created_at ? new Date(user.created_at).toLocaleDateString() : '--'}
            </span>
          </div>
          {isSystemAccount() && (
            <div className="flex items-center gap-3">
              <BadgeCheck className="w-4 h-4 text-emerald-500" />
              <span className="text-sm text-slate-500 w-24">System</span>
              <span className="text-sm text-emerald-600 dark:text-emerald-400">System Account</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}