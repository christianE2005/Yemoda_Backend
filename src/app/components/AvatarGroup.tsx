import { Tooltip, TooltipTrigger, TooltipContent } from './ui/tooltip';

interface AvatarUser {
  name: string;
  avatar?: string;
}

interface AvatarGroupProps {
  users: AvatarUser[];
  max?: number;
  size?: number;
}

export function AvatarGroup({ users, max = 3, size = 28 }: AvatarGroupProps) {
  const visible = users.slice(0, max);
  const overflow = users.length - max;

  return (
    <div className="flex items-center" style={{ marginLeft: 0 }}>
      {visible.map((user, i) => (
        <Tooltip key={i}>
          <TooltipTrigger asChild>
            <div
              className="rounded-full border-2 border-card bg-primary/10 flex items-center justify-center text-primary font-semibold shrink-0 cursor-default"
              style={{
                width: size,
                height: size,
                fontSize: size * 0.36,
                marginLeft: i > 0 ? -(size * 0.28) : 0,
                zIndex: max - i,
                position: 'relative',
              }}
            >
              {user.avatar ? (
                <img src={user.avatar} alt={user.name} className="w-full h-full rounded-full object-cover" />
              ) : (
                user.name.charAt(0).toUpperCase()
              )}
            </div>
          </TooltipTrigger>
          <TooltipContent className="text-xs">{user.name}</TooltipContent>
        </Tooltip>
      ))}
      {overflow > 0 && (
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              className="rounded-full border-2 border-card bg-muted flex items-center justify-center text-muted-foreground font-semibold shrink-0 cursor-default"
              style={{
                width: size,
                height: size,
                fontSize: size * 0.32,
                marginLeft: -(size * 0.28),
                zIndex: 0,
                position: 'relative',
              }}
            >
              +{overflow}
            </div>
          </TooltipTrigger>
          <TooltipContent className="text-xs">
            {users.slice(max).map((u) => u.name).join(', ')}
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}
