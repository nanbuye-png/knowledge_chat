import React from 'react'

function Placeholder({ title, desc }: { title: string; desc?: string }) {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">{title}</h1>
      <p className="text-slate-500 mt-2">{desc || 'Coming soon.'}</p>
    </div>
  )
}

export default function OrganizationDepartments() {
  return <Placeholder title="Departments & Groups" desc="Tree view of organization departments and groups." />
}