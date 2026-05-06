import { useState, useEffect, useMemo } from 'react';
import { Plus, Mail, User, Lock, Loader2, Shield, Pencil, Trash2, Search, X } from 'lucide-react';
import { useAuth, UserRole } from '../context/AuthContext';
import { usersService } from '../../services';
import { toast } from 'sonner';
import { motion } from 'motion/react';
import type { ApiUserAccount } from '../../services';
import {
  SYSTEM_ROLE_OPTIONS,
  USER_ROLE_TO_SYSTEM_ROLE,
  getSystemRoleLabel,
} from '../utils/roles';

interface NewUser {
  username: string;
  email: string;
  password: string;
  role: UserRole;
}

interface EditingUser {
  id: number;
  username: string;
  email: string;
  role: number;
  password?: string;
}

const BATCH_SIZE = 10;

export default function CreateUsers() {
  const { user: currentUser } = useAuth();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [formData, setFormData] = useState<NewUser>({
    username: '',
    email: '',
    password: '',
    role: 'user',
  });
  const [loading, setLoading] = useState(false);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [allUsers, setAllUsers] = useState<ApiUserAccount[]>([]);
  const [editingUser, setEditingUser] = useState<EditingUser | null>(null);
  const [editSaving, setEditSaving] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [roleFilter, setRoleFilter] = useState<number[]>([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [sortBy, setSortBy] = useState<'role' | 'name'>('role');
  const [showFilterPopup, setShowFilterPopup] = useState(false);

  useEffect(() => {
    // Only load users if the current user is an admin
    if (currentUser?.role === 'admin') {
      loadAllUsers();
    }
  }, [currentUser?.role]);

  const loadAllUsers = async () => {
    try {
      setLoadingUsers(true);
      const users = await usersService.list();
      setAllUsers(users);
      setCurrentPage(0);
    } catch (err) {
      console.error('[CreateUsers] Error loading users:', err);
      toast.error('Error al cargar usuarios');
    } finally {
      setLoadingUsers(false);
    }
  };

  // Filter and search users
  const filteredUsers = useMemo(() => {
    let users = allUsers.filter((user) => {
      const matchSearch = !searchTerm || 
        user.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
        user.email.toLowerCase().includes(searchTerm.toLowerCase());
      const matchRole = roleFilter.length === 0 || roleFilter.includes(user.system_role);
      return matchSearch && matchRole;
    });

    // Sort users
    if (sortBy === 'role') {
      const roleOrder: Record<number, number> = { 1: 0, 4: 1, 2: 2, 3: 3 };
      users.sort((a, b) => {
        const orderA = roleOrder[a.system_role] ?? 99;
        const orderB = roleOrder[b.system_role] ?? 99;
        if (orderA !== orderB) return orderA - orderB;
        return a.username.localeCompare(b.username);
      });
    } else if (sortBy === 'name') {
      users.sort((a, b) => a.username.localeCompare(b.username));
    }

    return users;
  }, [allUsers, searchTerm, roleFilter, sortBy]);

  // Paginate users
  const paginatedUsers = useMemo(() => {
    const start = currentPage * BATCH_SIZE;
    const end = start + BATCH_SIZE;
    return filteredUsers.slice(start, end);
  }, [filteredUsers, currentPage]);

  const totalPages = Math.ceil(filteredUsers.length / BATCH_SIZE);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleRoleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setFormData((prev) => ({ ...prev, role: e.target.value as UserRole }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.username || !formData.email || !formData.password) {
      toast.error('Por favor completa todos los campos');
      return;
    }

    // Email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(formData.email)) {
      toast.error('Por favor ingresa un correo electrónico válido');
      return;
    }

    if (formData.password.length < 8) {
      toast.error('La contraseña debe tener al menos 8 caracteres');
      return;
    }

    setLoading(true);
    try {
      await usersService.create({
        username: formData.username,
        email: formData.email,
        password: formData.password,
        system_role: getRoleSystemValue(formData.role),
      });

      toast.success(`Usuario ${formData.username} creado exitosamente`);
      setFormData({ username: '', email: '', password: '', role: 'user' });
      setShowCreateModal(false);
      await loadAllUsers();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al crear usuario';
      console.error('[CreateUsers] Error:', err);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleEditSave = async () => {
    if (!editingUser) return;

    if (editingUser.password && editingUser.password.length < 8) {
      toast.error('La contraseña debe tener al menos 8 caracteres');
      return;
    }

    if (currentUser?.id === String(editingUser.id)) {
      toast.error('No puedes editar tu propia cuenta');
      return;
    }

    setEditSaving(true);
    try {
      const updateData: any = {
        username: editingUser.username,
        email: editingUser.email,
        ...(editingUser.password ? { password: editingUser.password } : {}),
      };
      
      // Include system_role if it has been changed
      if (editingUser.role) {
        updateData.system_role = editingUser.role;
      }
      
      await usersService.update(editingUser.id, updateData);
      toast.success('Usuario actualizado exitosamente');
      setEditingUser(null);
      await loadAllUsers();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al actualizar usuario';
      console.error('[CreateUsers] Error updating:', err);
      toast.error(msg);
    } finally {
      setEditSaving(false);
    }
  };

  const handleDelete = async (userId: number) => {
    if (currentUser?.id === String(userId)) {
      toast.error('No puedes eliminar tu propia cuenta');
      return;
    }

    if (!confirm('¿Estás seguro de que deseas eliminar este usuario?')) {
      return;
    }

    try {
      await usersService.delete(userId);
      toast.success('Usuario eliminado exitosamente');
      await loadAllUsers();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al eliminar usuario';
      console.error('[CreateUsers] Error deleting:', err);
      toast.error(msg);
    }
  };

  const getRoleSystemValue = (role: UserRole): number => {
    return USER_ROLE_TO_SYSTEM_ROLE[role] ?? USER_ROLE_TO_SYSTEM_ROLE.user;
  };

  const getRoleColor = (roleId: number): string => {
    switch (roleId) {
      case 1:
        return 'bg-destructive/10 text-destructive';
      case 2:
        return 'bg-info/15 text-info';
      case 3:
        return 'bg-warning/15 text-warning';
      case 4:
        return 'bg-primary/15 text-primary';
      default:
        return 'bg-secondary';
    }
  };

  // Only allow admins
  if (currentUser?.role !== 'admin') {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-foreground mb-2">Acceso Denegado</h1>
          <p className="text-muted-foreground">
            Solo administradores pueden crear usuarios.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col px-4 pb-6 pt-3 max-w-[1600px] gap-4 h-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[13px] font-semibold text-foreground">Gestión de Usuarios</h1>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Crea y administra usuarios de la plataforma ({filteredUsers.length} total)
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-3 py-2 bg-primary hover:bg-primary-hover text-primary-foreground rounded-[3px] text-[12px] font-semibold transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          Nuevo Usuario
        </button>
      </div>

      {/* Search and Filters */}
      <div className="bg-card border border-border rounded-[3px] p-3">
        <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center relative">
          {/* Search bar */}
          <div className="flex-1 relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Buscar por nombre o email..."
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setCurrentPage(0);
              }}
              className="w-full bg-input-background border border-input rounded-[3px] pl-8 pr-3 py-2 text-[12px] text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
            />
          </div>

          {/* Filter Dropdown Button */}
          <div className="relative">
            <button
              onClick={() => setShowFilterPopup(!showFilterPopup)}
              className="bg-input-background border border-input rounded-[3px] px-3 py-2 text-[12px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary/20 hover:bg-secondary/30 transition-colors w-24"
            >
              Filtrar
            </button>

            {/* Filter Popup */}
            {showFilterPopup && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="absolute top-full mt-2 right-0 bg-card border border-border rounded-[3px] shadow-lg z-50 p-3 min-w-[280px]"
                onClick={(e) => e.stopPropagation()}
              >
                <style>{`
                  .filter-popup input[type="checkbox"],
                  .filter-popup input[type="radio"] {
                    accent-color: var(--primary);
                    cursor: pointer;
                  }
                `}</style>
                <div className="filter-popup space-y-3">
                  {/* Role Filter Section */}
                  <div>
                    <p className="text-[11px] font-semibold text-foreground/70 mb-2">FILTRAR POR ROL</p>
                    <div className="space-y-2">
                      <label className="flex items-center gap-2.5 px-2 py-1.5 rounded-[2px] hover:bg-secondary/50 transition-colors cursor-pointer">
                        <input
                          type="checkbox"
                          checked={roleFilter.length === 0}
                          onChange={() => {
                            setRoleFilter([]);
                            setCurrentPage(0);
                          }}
                          className="w-4 h-4 rounded-[2px] cursor-pointer"
                        />
                        <span className="text-[12px] text-foreground">Todos los roles</span>
                      </label>
                      {SYSTEM_ROLE_OPTIONS.map((role) => (
                        <label key={role.id} className="flex items-center gap-2.5 px-2 py-1.5 rounded-[2px] hover:bg-secondary/50 transition-colors cursor-pointer">
                          <input
                            type="checkbox"
                            checked={roleFilter.includes(role.id)}
                            onChange={() => {
                              setRoleFilter((prev) => {
                                if (prev.includes(role.id)) {
                                  return prev.filter((r) => r !== role.id);
                                } else {
                                  return [...prev, role.id];
                                }
                              });
                              setCurrentPage(0);
                            }}
                            className="w-4 h-4 rounded-[2px] cursor-pointer"
                          />
                          <span className="text-[12px] text-foreground">{role.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Sorting Section */}
                  <div className="border-t border-border pt-3">
                    <p className="text-[11px] font-semibold text-foreground/70 mb-2">ORDENAR POR</p>
                    <div className="space-y-2">
                      {[
                        { id: 'role', label: 'Rol' },
                        { id: 'name', label: 'Nombre' },
                      ].map((sort) => (
                        <label key={sort.id} className="flex items-center gap-2.5 px-2 py-1.5 rounded-[2px] hover:bg-secondary/50 transition-colors cursor-pointer">
                          <input
                            type="radio"
                            name="sort"
                            checked={sortBy === sort.id}
                            onChange={() => setSortBy(sort.id as 'role' | 'name')}
                            className="w-4 h-4 cursor-pointer"
                          />
                          <span className="text-[12px] text-foreground">{sort.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </div>
        </div>
      </div>

      {/* Close popup when clicking outside */}
      {showFilterPopup && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setShowFilterPopup(false)}
        />
      )}

      {/* Users List */}
      <div className="bg-card border border-border rounded-[3px] p-5 flex flex-col flex-1 min-h-0">
        <div className="flex items-center justify-between mb-3.5">
          <h2 className="text-[13px] font-semibold text-foreground">
            Usuarios {filteredUsers.length > 0 && `(${filteredUsers.length})`}
          </h2>
          {totalPages > 1 && (
            <span className="text-[11px] text-muted-foreground">
              Página {currentPage + 1} de {totalPages}
            </span>
          )}
        </div>

        {loadingUsers ? (
          <div className="space-y-2 flex-1">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 bg-secondary/30 rounded animate-pulse" />
            ))}
          </div>
        ) : filteredUsers.length === 0 ? (
          <div className="flex flex-col items-center justify-center flex-1 text-center">
            <div className="w-12 h-12 rounded-[3px] bg-primary/10 flex items-center justify-center mb-2.5">
              <User className="w-5 h-5 text-primary/40" />
            </div>
            <p className="text-[13px] text-muted-foreground">
              {searchTerm || roleFilter.length > 0 ? 'No hay usuarios que coincidan' : 'No hay usuarios en el sistema'}
            </p>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto pr-2 min-h-0" style={{
            scrollbarWidth: 'thin',
            scrollbarColor: 'var(--primary) var(--input-background)',
          }}>
            <style>{`
              .users-scroll::-webkit-scrollbar {
                width: 6px;
              }
              .users-scroll::-webkit-scrollbar-track {
                background: var(--input-background);
                border-radius: 3px;
              }
              .users-scroll::-webkit-scrollbar-thumb {
                background: var(--primary);
                border-radius: 3px;
              }
              .users-scroll::-webkit-scrollbar-thumb:hover {
                background: var(--primary-hover);
              }
            `}</style>
            <div className="users-scroll space-y-2 pr-1">
              {paginatedUsers.map((user) => {
                const isCurrentUser = currentUser?.id === String(user.id_user);
              const isEditing = editingUser?.id === user.id_user;

              return (
                <motion.div
                  key={user.id_user}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="p-3 rounded-[3px] border border-border hover:border-primary/40 hover:bg-accent/20 transition-colors"
                >
                  {isEditing && editingUser ? (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          value={editingUser.username}
                          onChange={(e) => setEditingUser({ ...editingUser, username: e.target.value })}
                          placeholder="Usuario"
                          className="flex-1 bg-input-background border border-input rounded-[3px] px-2.5 py-1.5 text-[12px] text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <input
                          type="email"
                          value={editingUser.email}
                          onChange={(e) => setEditingUser({ ...editingUser, email: e.target.value })}
                          placeholder="Correo"
                          className="flex-1 bg-input-background border border-input rounded-[3px] px-2.5 py-1.5 text-[12px] text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <select
                          value={editingUser.role}
                          onChange={(e) => setEditingUser({ ...editingUser, role: Number(e.target.value) })}
                          className="flex-1 bg-input-background border border-input rounded-[3px] px-2.5 py-1.5 text-[12px] text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 appearance-none"
                        >
                          {SYSTEM_ROLE_OPTIONS.map((role) => (
                            <option key={role.id} value={role.id}>{role.label}</option>
                          ))}
                        </select>
                      </div>
                      <div className="flex items-center gap-2">
                        <input
                          type="password"
                          value={editingUser.password ?? ''}
                          onChange={(e) => setEditingUser({ ...editingUser, password: e.target.value })}
                          placeholder="Nueva contraseña. Dejar vacío si no requiere cambios."
                          className="flex-1 bg-input-background border border-input rounded-[3px] px-2.5 py-1.5 text-[12px] text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                        />
                      </div>
                      <div className="flex items-center gap-2 pt-2 justify-end">
                        <button
                          onClick={() => setEditingUser(null)}
                          disabled={editSaving}
                          className="px-2.5 py-1 rounded-[3px] text-xs font-medium bg-secondary hover:bg-secondary/80 text-foreground transition-colors disabled:opacity-50"
                        >
                          Cancelar
                        </button>
                        <button
                          onClick={handleEditSave}
                          disabled={editSaving}
                          className="px-2.5 py-1 rounded-[3px] text-xs font-medium bg-primary hover:bg-primary-hover text-primary-foreground transition-colors disabled:opacity-50 flex items-center gap-1"
                        >
                          {editSaving && <Loader2 className="w-3 h-3 animate-spin" />}
                          Guardar
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <p className="text-[13px] font-medium text-foreground truncate">
                            {user.username}
                          </p>
                          {isCurrentUser && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/20 text-primary font-medium shrink-0">
                              Tú
                            </span>
                          )}
                        </div>
                        <p className="text-[12px] text-muted-foreground truncate mb-1.5">
                          {user.email}
                        </p>
                        <div className="flex items-center gap-2">
                          <span className={`inline-block px-2 py-0.5 rounded-[2px] text-[11px] font-medium ${getRoleColor(user.system_role)}`}>
                            {getSystemRoleLabel(user.system_role, user.system_role_name)}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1 ml-3 flex-shrink-0">
                        {!isCurrentUser && (
                          <>
                            <button
                              onClick={() => setEditingUser({
                                id: user.id_user,
                                username: user.username,
                                email: user.email,
                                role: user.system_role,
                              })}
                              className="p-1.5 rounded-[3px] hover:bg-primary/10 text-primary/60 hover:text-primary transition-colors"
                              title="Editar"
                            >
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => handleDelete(user.id_user)}
                              className="p-1.5 rounded-[3px] hover:bg-destructive/10 text-destructive/60 hover:text-destructive transition-colors"
                              title="Eliminar"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </motion.div>
              );
            })}
            </div>
          </div>
        )}

        {/* Pagination */}
        <div className="border-t border-border pt-3 mt-3 flex items-center justify-center gap-2">
          <button
            onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
            disabled={currentPage === 0 || totalPages <= 1}
            className="px-3 py-1.5 rounded-[3px] text-[12px] font-medium bg-secondary hover:bg-secondary/80 text-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Anterior
          </button>
          {Array.from({ length: totalPages }).map((_, i) => (
            <button
              key={i}
              onClick={() => setCurrentPage(i)}
              className={`px-2.5 py-1.5 rounded-[3px] text-[12px] font-medium transition-colors ${
                currentPage === i
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-secondary hover:bg-secondary/80 text-foreground'
              }`}
            >
              {i + 1}
            </button>
          ))}
          <button
            onClick={() => setCurrentPage(Math.min(totalPages - 1, currentPage + 1))}
            disabled={currentPage === totalPages - 1 || totalPages <= 1}
            className="px-3 py-1.5 rounded-[3px] text-[12px] font-medium bg-secondary hover:bg-secondary/80 text-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Siguiente
          </button>
        </div>
      </div>

      {/* Create User Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-card border border-border rounded-[4px] p-6 max-w-lg w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[15px] font-semibold text-foreground">Crear Nuevo Usuario</h2>
              <button
                onClick={() => setShowCreateModal(false)}
                className="inline-flex h-8 items-center justify-center rounded-[4px] border border-border bg-card px-3 text-[11px] font-medium text-foreground shadow-sm transition-colors hover:bg-surface-secondary"
              >
                <X className="mr-1 w-4 h-4" /> Cerrar
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Username */}
              <div>
                <label className="block text-[12px] font-medium text-foreground mb-1.5">
                  Nombre de Usuario
                </label>
                <div className="relative">
                  <User className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    type="text"
                    name="username"
                    value={formData.username}
                    onChange={handleInputChange}
                    placeholder="juan.perez"
                    className="w-full bg-input-background border border-input rounded-[3px] pl-8 pr-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
                    autoFocus
                  />
                </div>
              </div>

              {/* Email */}
              <div>
                <label className="block text-[12px] font-medium text-foreground mb-1.5">
                  Correo Electrónico
                </label>
                <div className="relative">
                  <Mail className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    type="email"
                    name="email"
                    value={formData.email}
                    onChange={handleInputChange}
                    placeholder="juan@techmahindra.com"
                    className="w-full bg-input-background border border-input rounded-[3px] pl-8 pr-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
                  />
                </div>
              </div>

              {/* Password */}
              <div>
                <label className="block text-[12px] font-medium text-foreground mb-1.5">
                  Contraseña Temporal
                </label>
                <div className="relative">
                  <Lock className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    type="password"
                    name="password"
                    value={formData.password}
                    onChange={handleInputChange}
                    placeholder="••••••••"
                    className="w-full bg-input-background border border-input rounded-[3px] pl-8 pr-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
                  />
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Mínimo 8 caracteres
                </p>
              </div>

              {/* Role */}
              <div>
                <label className="block text-[12px] font-medium text-foreground mb-1.5">
                  Rol
                </label>
                <div className="relative">
                  <Shield className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <select
                    value={formData.role}
                    onChange={handleRoleChange}
                    className="w-full bg-input-background border border-input rounded-[3px] pl-8 pr-3 py-2 text-[13px] text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors appearance-none"
                  >
                    {SYSTEM_ROLE_OPTIONS.map((role) => (
                      <option key={role.id} value={role.role}>{role.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Buttons */}
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="flex-1 px-3 py-2 rounded-[3px] border border-border text-[12px] font-medium text-foreground hover:bg-surface-secondary transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 px-3 py-2 bg-primary hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed text-primary-foreground rounded-[3px] text-[12px] font-semibold transition-colors flex items-center justify-center gap-2"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Creando...
                    </>
                  ) : (
                    <>
                      <Plus className="w-3.5 h-3.5" />
                      Crear Usuario
                    </>
                  )}
                </button>
              </div>
            </form>
          </motion.div>
        </div>
      )}
    </div>
  );
}
