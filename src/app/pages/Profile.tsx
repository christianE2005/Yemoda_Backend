import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { User, Mail, Shield, Moon, Sun, Lock, Loader2, KeyRound, X } from 'lucide-react';
import { toast } from 'sonner';
import { motion } from 'motion/react';
import { useApiProjectMembers, useApiProjects } from '../hooks/useProjectData';
import { StatusBadge } from '../components/StatusBadge';
import { GitHubConnectSection } from '../components/GitHubConnectSection';
import { usersService } from '../../services';
import { getUserRoleLabel } from '../utils/roles';
import { compareProjectsForGenericPriority, getProjectStatusBadge, getProjectStatusLabel, shouldShowInGenericProjectDisplays } from '../utils/projectStatus';
import { formatProjectDate, getProjectDaysLabel } from '../utils/projectDates';

export default function Profile() {
  const navigate = useNavigate();
  const { user, syncUser } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showSecurityModal, setShowSecurityModal] = useState(false);
  const [securitySaving, setSecuritySaving] = useState(false);
  const [formData, setFormData] = useState({
    name: user?.name || '',
    email: user?.email || '',
  });
  const [passwordData, setPasswordData] = useState({
    password: '',
    confirmPassword: '',
  });

  const userId = Number(user?.id ?? 0);
  const { data: projects, loading: loadingProjects } = useApiProjects();
  const { data: memberRows, loading: loadingMemberRows } = useApiProjectMembers(undefined, userId > 0 ? userId : undefined);
  const visibleProjects = useMemo(() => {
    const allowedProjectIds = new Set((memberRows ?? []).map((member) => member.project));
    return (projects ?? []).filter((project) => allowedProjectIds.has(project.id_project));
  }, [projects, memberRows]);
  const genericProjects = useMemo(
    () => [...visibleProjects].filter((project) => shouldShowInGenericProjectDisplays(project.status)).sort(compareProjectsForGenericPriority),
    [visibleProjects],
  );
  const profileProjects = genericProjects.slice(0, 6);
  useEffect(() => {
    setFormData({
      name: user?.name || '',
      email: user?.email || '',
    });
  }, [user?.name, user?.email]);

  const roleLabel = useMemo(() => (user ? getUserRoleLabel(user.role) : 'Usuario'), [user]);

  const resetEditingState = () => {
    setFormData({
      name: user?.name || '',
      email: user?.email || '',
    });
    setEditing(false);
  };

  const handleSave = async () => {
    if (!userId) return;

    const trimmedName = formData.name.trim();
    const trimmedEmail = formData.email.trim();

    if (!trimmedName || !trimmedEmail) {
      toast.error('Nombre y correo son obligatorios');
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(trimmedEmail)) {
      toast.error('Por favor ingresa un correo electrónico válido');
      return;
    }

    setSaving(true);
    try {
      const updatedUser = await usersService.update(userId, {
        username: trimmedName,
        email: trimmedEmail,
      });
      syncUser(updatedUser);
      setEditing(false);
      toast.success('Perfil actualizado exitosamente');
    } catch {
      toast.error('Error al actualizar el perfil');
    } finally {
      setSaving(false);
    }
  };

  const handleSecuritySave = async () => {
    if (!userId) return;

    if (!passwordData.password || !passwordData.confirmPassword) {
      toast.error('Completa ambos campos de contraseña');
      return;
    }

    if (passwordData.password.length < 8) {
      toast.error('La contraseña debe tener al menos 8 caracteres');
      return;
    }

    if (passwordData.password !== passwordData.confirmPassword) {
      toast.error('Las contraseñas no coinciden');
      return;
    }

    setSecuritySaving(true);
    try {
      await usersService.update(userId, { password: passwordData.password });
      setPasswordData({ password: '', confirmPassword: '' });
      setShowSecurityModal(false);
      toast.success('Contraseña actualizada exitosamente');
    } catch {
      toast.error('Error al actualizar la contraseña');
    } finally {
      setSecuritySaving(false);
    }
  };

  return (
    <div className="px-4 pb-6 pt-3 max-w-[1600px]">
      <h1 className="text-[13px] font-semibold text-foreground mb-0.5">Mi Perfil</h1>
      <p className="text-[11px] text-muted-foreground mb-4">Información y preferencias</p>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">

          {/* Basic Info */}
          <div className="bg-card border border-border border-l-[3px] border-l-primary rounded-[4px] p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-[12px] font-semibold text-foreground">Información Personal</h2>
              <div className="flex items-center gap-2">
                {editing && (
                  <button
                    onClick={resetEditingState}
                    className="px-3 py-1.5 rounded-md text-xs font-medium bg-secondary hover:bg-accent text-foreground transition-colors"
                  >
                    Cancelar
                  </button>
                )}
                <button
                  onClick={editing ? handleSave : () => setEditing(true)}
                  disabled={saving}
                  className="px-3 py-1.5 rounded-md text-xs font-medium bg-primary hover:bg-primary-hover text-primary-foreground transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
                >
                  {saving && <Loader2 className="w-3 h-3 animate-spin" />}
                  {editing ? (saving ? 'Guardando…' : 'Guardar cambios') : 'Editar'}
                </button>
              </div>
            </div>

            <div className="flex items-center gap-3 mb-4 pb-4 border-b border-border">
              <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                <span className="text-primary text-base font-semibold">
                  {(user?.name ?? 'U').charAt(0).toUpperCase()}
                </span>
              </div>
              <div>
                <h3 className="text-[13px] font-semibold text-foreground">{user?.name}</h3>
                <p className="text-[10px] text-muted-foreground">{roleLabel}</p>
              </div>
            </div>

            <div className="space-y-2.5">
              <div>
                <label className="block text-[11px] font-medium text-foreground mb-1">
                  <User className="w-3 h-3 inline mr-1" /> Nombre
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  disabled={!editing}
                  className="w-full h-7 bg-surface-secondary border border-border rounded-[3px] px-2.5 text-[11px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary/20 disabled:opacity-50"
                />
              </div>
              <div>
                <label className="block text-[11px] font-medium text-foreground mb-1">
                  <Mail className="w-3 h-3 inline mr-1" /> Correo
                </label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  disabled={!editing}
                  className="w-full h-7 bg-surface-secondary border border-border rounded-[3px] px-2.5 text-[11px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary/20 disabled:opacity-50"
                />
              </div>
              <div>
                <label className="block text-[11px] font-medium text-foreground mb-1">
                  <Shield className="w-3 h-3 inline mr-1" /> Rol
                </label>
                <div className="w-full h-7 bg-surface-secondary border border-border rounded-[3px] px-2.5 text-[11px] text-muted-foreground capitalize flex items-center">
                  {roleLabel}
                </div>
              </div>
            </div>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.1 }}
            className="bg-card border border-border rounded-[4px] overflow-hidden"
          >
            <div className="px-4 py-3 border-b border-border">
              <h2 className="text-[12px] font-semibold text-foreground">Mis Proyectos</h2>
            </div>
            {loadingProjects || loadingMemberRows ? (
              <div className="p-4 space-y-2">
                {[1, 2, 3].map((i) => <div key={i} className="h-8 animate-pulse bg-secondary rounded" />)}
              </div>
            ) : profileProjects.length === 0 ? (
              <div className="py-12 text-center">
                <p className="text-[11px] text-muted-foreground">No hay proyectos activos para mostrar.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full table-fixed min-w-[520px]">
                  <colgroup>
                    <col className="w-[40%]" />
                    <col className="w-[24%]" />
                    <col className="w-[22%]" />
                    <col className="w-[14%]" />
                  </colgroup>
                  <thead>
                    <tr className="border-b border-border bg-surface-secondary/50">
                      <th className="text-left py-1.5 px-4 text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Proyecto</th>
                      <th className="text-left py-1.5 px-3 text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Estado</th>
                      <th className="text-left py-1.5 px-3 text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Fecha Fin</th>
                      <th className="text-left py-1.5 px-3 text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Días rest.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {profileProjects.map((project, i) => {
                      const dl = getProjectDaysLabel(project.end_date, project.status);
                      return (
                        <motion.tr
                          key={project.id_project}
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.25, delay: i * 0.04, ease: 'easeOut' }}
                          className="border-b border-border last:border-0 hover:bg-accent/30 transition-colors group cursor-pointer"
                          onClick={() => navigate(`/projects/${project.id_project}`)}
                        >
                          <td className="py-1.5 px-4">
                            <p className="text-[12px] font-medium text-foreground truncate">{project.name}</p>
                          </td>
                          <td className="py-1.5 px-3">
                            <StatusBadge status={getProjectStatusBadge(project.status)} text={getProjectStatusLabel(project.status)} size="sm" />
                          </td>
                          <td className="py-1.5 px-3 text-[11px] text-muted-foreground whitespace-nowrap">{formatProjectDate(project.end_date)}</td>
                          <td className="py-1.5 px-3">
                            <span className={`text-[12px] ${dl.cls}`}>{dl.label}</span>
                          </td>
                        </motion.tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </motion.div>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <div className="bg-card border border-border rounded-[4px] p-4">
            <h2 className="text-[12px] font-semibold text-foreground mb-2">Preferencias</h2>
            <button
              onClick={toggleTheme}
              className="w-full flex items-center justify-between p-2.5 border border-border rounded-[4px] hover:border-primary/30 transition-colors"
            >
              <div className="flex items-center gap-2">
                {theme === 'dark' ? <Moon className="w-3.5 h-3.5" /> : <Sun className="w-3.5 h-3.5" />}
                <div className="text-left">
                  <p className="text-[12px] font-medium text-foreground">Tema</p>
                  <p className="text-[10px] text-muted-foreground">{theme === 'dark' ? 'Oscuro' : 'Claro'}</p>
                </div>
              </div>
              <div className={`w-9 h-5 rounded-full transition-colors flex items-center shadow-inner ${theme === 'dark' ? 'bg-primary' : 'bg-muted'}`}>
                <div className={`w-4 h-4 bg-white rounded-full shadow transition-all ${theme === 'dark' ? 'ml-auto mr-0.5' : 'ml-0.5 mr-auto'}`} />
              </div>
            </button>
          </div>

          <div className="bg-card border border-border rounded-[4px] p-4">
            <h2 className="text-[12px] font-semibold text-foreground mb-2">Seguridad</h2>
            <div className="rounded-[4px] border border-border p-3 bg-surface-secondary/30">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-2">
                  <Lock className="w-3.5 h-3.5 text-muted-foreground mt-0.5" />
                  <div>
                    <p className="text-[12px] font-medium text-foreground">Contraseña</p>
                    <p className="text-[10px] text-muted-foreground">
                      Gestiona tus credenciales desde una ventana independiente.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setShowSecurityModal(true)}
                  className="h-7 px-3 bg-primary hover:bg-primary-hover text-primary-foreground rounded-[3px] text-[11px] font-medium transition-colors inline-flex items-center gap-1.5"
                >
                  <KeyRound className="w-3.5 h-3.5" />
                  Cambiar
                </button>
              </div>
            </div>
          </div>

          <div className="bg-card border border-border rounded-[4px] p-4">
            <h2 className="text-[12px] font-semibold text-foreground mb-3">GitHub</h2>
            <GitHubConnectSection />
          </div>
        </div>
      </div>

      {showSecurityModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-6">
          <div className="bg-card border border-border rounded-[4px] p-5 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-[13px] font-semibold text-foreground">Actualizar contraseña</h2>
                <p className="text-[11px] text-muted-foreground mt-0.5">Este cambio es independiente de la edición del perfil.</p>
              </div>
              <button type="button" onClick={() => setShowSecurityModal(false)} className="inline-flex h-8 items-center justify-center rounded-[4px] border border-border bg-card px-3 text-[11px] font-medium text-foreground shadow-sm transition-colors hover:bg-surface-secondary">
                <X className="mr-1 w-3.5 h-3.5" /> Cerrar
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-[11px] font-medium text-foreground mb-1">Nueva contraseña</label>
                <input
                  type="password"
                  value={passwordData.password}
                  onChange={(e) => setPasswordData((prev) => ({ ...prev, password: e.target.value }))}
                  placeholder="Minimo 8 caracteres"
                  className="w-full h-8 bg-surface-secondary border border-border rounded-[3px] px-2.5 text-[12px] text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="block text-[11px] font-medium text-foreground mb-1">Confirmar contraseña</label>
                <input
                  type="password"
                  value={passwordData.confirmPassword}
                  onChange={(e) => setPasswordData((prev) => ({ ...prev, confirmPassword: e.target.value }))}
                  placeholder="Repite la nueva contraseña"
                  className="w-full h-8 bg-surface-secondary border border-border rounded-[3px] px-2.5 text-[12px] text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
                />
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setPasswordData({ password: '', confirmPassword: '' });
                    setShowSecurityModal(false);
                  }}
                  className="flex-1 h-8 border border-border rounded-[3px] text-[11px] font-medium text-foreground hover:bg-surface-secondary transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  onClick={handleSecuritySave}
                  disabled={securitySaving}
                  className="flex-1 h-8 bg-primary hover:bg-primary-hover text-primary-foreground rounded-[3px] text-[11px] font-medium transition-colors disabled:opacity-50 inline-flex items-center justify-center gap-1.5"
                >
                  {securitySaving && <Loader2 className="w-3 h-3 animate-spin" />}
                  {securitySaving ? 'Guardando…' : 'Guardar'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
