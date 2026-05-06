import { Skeleton } from './ui/skeleton';

/** Reusable skeleton for KPI stat cards (Dashboard, ProjectDetail) */
export function KPICardSkeleton() {
  return (
    <div className="bg-card border border-border rounded-lg p-5">
      <div className="flex items-center justify-between mb-3">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-5 w-5 rounded" />
      </div>
      <Skeleton className="h-7 w-24 mb-2" />
      <Skeleton className="h-3 w-16" />
    </div>
  );
}

/** Skeleton for project cards in the Projects page */
export function ProjectCardSkeleton() {
  return (
    <div className="bg-card border border-border rounded-lg p-5 space-y-4">
      <div className="flex items-center justify-between">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-5 w-20 rounded-md" />
      </div>
      <Skeleton className="h-3 w-full" />
      <div className="space-y-2">
        <div className="flex justify-between">
          <Skeleton className="h-3 w-14" />
          <Skeleton className="h-3 w-10" />
        </div>
        <Skeleton className="h-1.5 w-full rounded-full" />
      </div>
      <div className="flex items-center justify-between pt-1">
        <div className="flex items-center gap-3">
          <Skeleton className="h-3 w-12" />
          <Skeleton className="h-3 w-10" />
          <Skeleton className="h-3 w-20" />
        </div>
      </div>
      <div className="flex items-center justify-between">
        <Skeleton className="h-3 w-28" />
        <div className="flex gap-1.5">
          <Skeleton className="h-5 w-12 rounded" />
          <Skeleton className="h-5 w-12 rounded" />
        </div>
      </div>
    </div>
  );
}

/** Skeleton for kanban column */
function KanbanColumnSkeleton() {
  return (
    <div className="flex-1 min-w-[280px] space-y-3">
      <div className="flex items-center gap-2 mb-4">
        <Skeleton className="w-2 h-2 rounded-full" />
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-3 w-4" />
      </div>
      {[1, 2, 3].map((i) => (
        <div key={i} className="bg-card border border-border rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Skeleton className="w-2 h-2 rounded-full" />
            <Skeleton className="h-4 w-40" />
          </div>
          <Skeleton className="h-3 w-full" />
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-3 w-16" />
            </div>
            <Skeleton className="h-5 w-12 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Page-level skeletons composed from above building blocks */

export function DashboardSkeleton() {
  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-6 animate-in fade-in duration-300">
      {/* Header */}
      <div className="space-y-1">
        <Skeleton className="h-7 w-40" />
        <Skeleton className="h-4 w-64" />
      </div>
      {/* KPI row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => <KPICardSkeleton key={i} />)}
      </div>
      {/* Chart area */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-card border border-border rounded-lg p-5">
          <Skeleton className="h-5 w-36 mb-4" />
          <Skeleton className="h-[200px] w-full rounded-md" />
        </div>
        <div className="bg-card border border-border rounded-lg p-5 space-y-4">
          <Skeleton className="h-5 w-28" />
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex items-center gap-3">
              <Skeleton className="w-2 h-2 rounded-full" />
              <Skeleton className="h-3 flex-1" />
              <Skeleton className="h-3 w-10" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ProjectsSkeleton() {
  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <Skeleton className="h-7 w-32" />
          <Skeleton className="h-4 w-56" />
        </div>
        <Skeleton className="h-9 w-36 rounded-md" />
      </div>
      {/* Search + filters */}
      <div className="flex items-center gap-4">
        <Skeleton className="h-9 flex-1 max-w-md rounded-md" />
        <Skeleton className="h-9 w-64 rounded-md" />
      </div>
      {/* Cards grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3, 4, 5, 6].map((i) => <ProjectCardSkeleton key={i} />)}
      </div>
    </div>
  );
}

export function BacklogSkeleton() {
  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <Skeleton className="h-7 w-28" />
          <Skeleton className="h-4 w-52" />
        </div>
        <Skeleton className="h-9 w-32 rounded-md" />
      </div>
      <div className="flex gap-4 overflow-hidden">
        {[1, 2, 3].map((i) => <KanbanColumnSkeleton key={i} />)}
      </div>
    </div>
  );
}

export function GenericPageSkeleton() {
  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-6 animate-in fade-in duration-300">
      <div className="space-y-1">
        <Skeleton className="h-7 w-40" />
        <Skeleton className="h-4 w-60" />
      </div>
      <div className="bg-card border border-border rounded-lg p-6 space-y-4">
        <Skeleton className="h-5 w-44" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-lg p-6 space-y-3">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-[120px] w-full rounded-md" />
        </div>
        <div className="bg-card border border-border rounded-lg p-6 space-y-3">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-[120px] w-full rounded-md" />
        </div>
      </div>
    </div>
  );
}
