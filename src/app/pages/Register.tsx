import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router';
import { Eye, EyeOff, Lock, Mail, User, ArrowRight, Shield, Clock, Users, Check, X, Briefcase } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { LoadingButton } from '../components/LoadingButton';
import { usersService } from '../../services';
import type { ApiSystemRole } from '../../services/types';
import { toast } from 'sonner';

export default function Register() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [selectedRoleId, setSelectedRoleId] = useState<number | ''>('');
  const [systemRoles, setSystemRoles] = useState<ApiSystemRole[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const { register } = useAuth();

  useEffect(() => {
    usersService.listSystemRoles()
      .then(setSystemRoles)
      .catch(() => {
        // Fallback: known roles if endpoint requires auth
        setSystemRoles([
          { id_system_role: 1, name: 'Admin', description: 'Administrador del sistema' },
          { id_system_role: 2, name: 'User', description: 'Usuario de la plataforma' },
          { id_system_role: 3, name: 'Stakeholder', description: 'Usuario con acceso de consulta' },
          { id_system_role: 4, name: 'Project Manager', description: 'Gestor de proyectos' },
        ]);
      });
  }, []);

  const getPasswordStrength = (pwd: string) => {
    let s = 0;
    if (pwd.length >= 8) s++;
    if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) s++;
    if (/\d/.test(pwd)) s++;
    if (/[^a-zA-Z0-9]/.test(pwd)) s++;
    return s;
  };

  const passwordStrength = getPasswordStrength(password);
  const strengthLabels = ['Muy débil', 'Débil', 'Media', 'Fuerte', 'Muy fuerte'];
  const strengthColors = ['bg-destructive', 'bg-warning', 'bg-warning', 'bg-success', 'bg-success'];

  const ALLOWED_DOMAIN = '@techmahindra.com';
  const isEmailValid = email === '' || email.toLowerCase().endsWith(ALLOWED_DOMAIN);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !email || !password || !confirmPassword) {
      toast.error('Por favor completa todos los campos');
      return;
    }
    if (!selectedRoleId) {
      toast.error('Por favor selecciona un rol');
      return;
    }
    if (!email.toLowerCase().endsWith(ALLOWED_DOMAIN)) {
      toast.error('Solo se permiten correos @techmahindra.com');
      return;
    }
    if (password !== confirmPassword) {
      toast.error('Las contraseñas no coinciden');
      return;
    }
    if (passwordStrength < 2) {
      toast.error('La contraseña es muy débil');
      return;
    }
    setIsLoading(true);
    try {
      await register(name, email, password, selectedRoleId || undefined);
      toast.success('¡Cuenta creada exitosamente!');
      navigate('/dashboard');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al crear cuenta';
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const inputClass = 'w-full bg-input-background border border-input rounded-[3px] pl-8 pr-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors';

  return (
    <div className="min-h-screen flex">
      {/* Left Panel */}
      <div className="hidden lg:flex lg:w-[420px] xl:w-[480px] bg-[#010409] border-r border-[#21262D] flex-col justify-between p-10">
        <div>
          <Link to="/" className="flex items-center gap-2 mb-14">
            <div className="w-8 h-8 bg-primary rounded-[3px] flex items-center justify-center">
              <span className="text-white font-bold text-xs">PI</span>
            </div>
            <div>
              <p className="text-[13px] font-bold text-white leading-tight">Project Intelligence</p>
              <p className="text-[10px] text-[#8B949E] leading-tight">Tech Mahindra</p>
            </div>
          </Link>

          <h2 className="text-[22px] font-bold text-white leading-snug mb-3">
            Únete al equipo de<br />
            <span className="text-primary">Project Intelligence</span>
          </h2>
          <p className="text-[13px] text-[#8B949E] leading-relaxed mb-10">
            Crea tu cuenta y comienza a gestionar los proyectos de Tech Mahindra con inteligencia en menos de 2 minutos.
          </p>

          <div className="space-y-4">
            {[
              { icon: <Shield className="w-3.5 h-3.5" />, title: 'Configuración segura', desc: 'Encriptación de datos y acceso por roles' },
              { icon: <Clock className="w-3.5 h-3.5" />, title: 'Listo en minutos', desc: 'Sin configuración compleja para comenzar' },
              { icon: <Users className="w-3.5 h-3.5" />, title: 'Colaboración total', desc: 'Invita a tu equipo y asigna permisos' },
            ].map((f, i) => (
              <div key={i} className="flex items-start gap-3">
                <div className="w-7 h-7 rounded-[3px] bg-primary/15 flex items-center justify-center text-primary shrink-0 mt-0.5 border border-primary/20">
                  {f.icon}
                </div>
                <div>
                  <p className="text-[12px] font-semibold text-white">{f.title}</p>
                  <p className="text-[11px] text-[#8B949E] mt-0.5">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="text-[11px] text-[#8B949E]">&copy; 2026 Tech Mahindra</p>
      </div>

      {/* Right Panel */}
      <div className="flex-1 flex items-center justify-center p-6 bg-background">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="lg:hidden text-center mb-8">
            <Link to="/" className="inline-flex items-center gap-2">
              <div className="w-8 h-8 bg-primary rounded-[3px] flex items-center justify-center">
                <span className="text-white font-bold text-xs">PI</span>
              </div>
              <span className="font-bold text-foreground text-sm">Project Intelligence</span>
            </Link>
          </div>

          <div className="mb-7">
            <h1 className="text-[18px] font-bold text-foreground mb-1">Crear Cuenta</h1>
            <p className="text-[13px] text-muted-foreground">Completa tus datos para comenzar</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Name */}
            <div>
              <label className="block text-[12px] font-medium text-foreground mb-1.5">Nombre completo</label>
              <div className="relative">
                <User className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Juan Pérez"
                  className={inputClass}
                />
              </div>
            </div>

            {/* Email */}
            <div>
              <label className="block text-[12px] font-medium text-foreground mb-1.5">Correo electrónico</label>
              <div className="relative">
                <Mail className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="usuario@techmahindra.com"
                  className={`${inputClass} ${email && !isEmailValid ? 'border-destructive focus:ring-destructive/30 focus:border-destructive' : ''}`}
                />
              </div>
              {email && !isEmailValid && (
                <p className="mt-1.5 text-[10px] text-destructive flex items-center gap-1">
                  <X className="w-3 h-3" /> Solo se permiten correos @techmahindra.com
                </p>
              )}
            </div>

            {/* Password */}
            <div>
              <label className="block text-[12px] font-medium text-foreground mb-1.5">Contraseña</label>
              <div className="relative">
                <Lock className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-input-background border border-input rounded-[3px] pl-8 pr-10 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>
              {password && (
                <div className="mt-2">
                  <div className="flex gap-0.5 mb-1">
                    {[0, 1, 2, 3].map((i) => (
                      <div
                        key={i}
                        className={`h-0.5 flex-1 rounded-full transition-colors ${
                          i < passwordStrength ? strengthColors[passwordStrength] : 'bg-input'
                        }`}
                      />
                    ))}
                  </div>
                  <p className={`text-[10px] ${passwordStrength < 2 ? 'text-destructive' : passwordStrength < 3 ? 'text-warning' : 'text-success'}`}>
                    Fortaleza: {strengthLabels[passwordStrength]}
                  </p>
                </div>
              )}
            </div>

            {/* Confirm Password */}
            <div>
              <label className="block text-[12px] font-medium text-foreground mb-1.5">Confirmar contraseña</label>
              <div className="relative">
                <Lock className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <input
                  type={showConfirmPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-input-background border border-input rounded-[3px] pl-8 pr-10 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  aria-label={showConfirmPassword ? 'Ocultar confirmación' : 'Mostrar confirmación'}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showConfirmPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>
              {confirmPassword && (
                <div className="mt-1.5 flex items-center gap-1.5">
                  {password === confirmPassword ? (
                    <><Check className="w-3 h-3 text-success" /><span className="text-[10px] text-success">Las contraseñas coinciden</span></>
                  ) : (
                    <><X className="w-3 h-3 text-destructive" /><span className="text-[10px] text-destructive">Las contraseñas no coinciden</span></>
                  )}
                </div>
              )}
            </div>

            {/* Role Selector */}
            <div>
              <label className="block text-[12px] font-medium text-foreground mb-1.5">Rol en el sistema</label>
              <div className="relative">
                <Briefcase className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <select
                  value={selectedRoleId}
                  onChange={(e) => setSelectedRoleId(e.target.value ? Number(e.target.value) : '')}
                  className={`${inputClass} appearance-none cursor-pointer`}
                >
                  <option value="">Selecciona tu rol</option>
                  {systemRoles.map((role) => (
                    <option key={role.id_system_role} value={role.id_system_role}>
                      {role.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Submit */}
            <LoadingButton
              type="submit"
              loading={isLoading}
              className="w-full bg-primary hover:bg-primary-hover text-white rounded-[3px] py-2.5 text-[13px] font-semibold transition-colors flex items-center justify-center gap-2"
            >
              Crear Cuenta
              <ArrowRight className="w-3.5 h-3.5" />
            </LoadingButton>
          </form>

          <p className="text-center text-[12px] text-muted-foreground mt-6">
            ¿Ya tienes cuenta?{' '}
            <Link to="/login" className="text-primary hover:underline font-medium">Inicia sesión</Link>
          </p>

          <div className="text-center mt-4">
            <Link to="/" className="text-[11px] text-muted-foreground hover:text-foreground transition-colors">
              ← Volver al inicio
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}