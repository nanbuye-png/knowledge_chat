import React from 'react'

function Placeholder({ title, desc }: { title: string; desc?: string }) {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">{title}</h1>
      <p className="text-slate-500 mt-2">{desc || 'Coming soon.'}</p>
    </div>
  )
}

export default function OrganizationMembers() {
  return <Placeholder title="Organization Members" desc="Manage organization members and their roles." />
}