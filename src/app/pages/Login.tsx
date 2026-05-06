import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { Eye, EyeOff, Lock, Mail, ArrowRight, BarChart3, Bell, Brain } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { LoadingButton } from '../components/LoadingButton';
import { toast } from 'sonner';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error('Por favor completa todos los campos');
      return;
    }
    setIsLoading(true);
    try {
      await login(email, password);
      toast.success('¡Bienvenido a PI Platform!');
      navigate('/dashboard');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al iniciar sesión';
      console.error(`[Login] Error:`, err);
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left Panel — Dark branding */}
      <div className="hidden lg:flex lg:w-[420px] xl:w-[480px] bg-[#010409] flex-col justify-between p-10 border-r border-[#21262D]">
        <div>
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2 mb-14">
            <div className="w-8 h-8 bg-primary rounded-[3px] flex items-center justify-center">
              <span className="text-white font-bold text-xs">PI</span>
            </div>
            <div>
              <p className="text-[13px] font-bold text-white leading-tight">Project Intelligence</p>
              <p className="text-[10px] text-[#8B949E] leading-tight">ABCDH Technologies</p>
            </div>
          </Link>

          <h2 className="text-[22px] font-bold text-white leading-snug mb-3">
            Gestión Inteligente de<br />
            <span className="text-primary">Proyectos en Tiempo Real</span>
          </h2>
          <p className="text-[13px] text-[#8B949E] leading-relaxed mb-10">
            Centraliza, monitorea y analiza el estado de tus proyectos. La plataforma corporativa impulsada por IA que ejecutivos y equipos necesitan.
          </p>

          {/* Feature highlights */}
          <div className="space-y-4">
            {[
              { icon: <BarChart3 className="w-3.5 h-3.5" />, title: 'KPIs en tiempo real', desc: 'Métricas de avance y presupuesto actualizadas' },
              { icon: <Bell className="w-3.5 h-3.5" />, title: 'Alertas tempranas', desc: 'Notificaciones inteligentes de riesgos' },
              { icon: <Brain className="w-3.5 h-3.5" />, title: 'Análisis predictivo', desc: 'Predicción de retrasos y desviaciones presupuestales' },
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

          <p className="text-[11px] text-[#8B949E]">&copy; 2026 ABCDH Technologies</p>
      </div>

      {/* Right Panel — Form */}
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
            <h1 className="text-[18px] font-bold text-foreground mb-1">Iniciar Sesión</h1>
            <p className="text-[13px] text-muted-foreground">Accede a tu panel de gestión de proyectos</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label className="block text-[12px] font-medium text-foreground mb-1.5">
                Correo electrónico
              </label>
              <div className="relative">
                <Mail className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="usuario@abcdhtechnologies.com"
                  className="w-full bg-input-background border border-input rounded-[3px] pl-8 pr-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="block text-[12px] font-medium text-foreground mb-1.5">
                Contraseña
              </label>
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
            </div>

            {/* Remember & Forgot */}
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" className="w-3.5 h-3.5 rounded-[3px] border-input accent-primary" />
                <span className="text-[12px] text-muted-foreground">Recordarme</span>
              </label>
              <a href="#" className="text-[12px] text-primary hover:underline font-medium">
                ¿Olvidaste tu contraseña?
              </a>
            </div>

            {/* Submit */}
            <LoadingButton
              type="submit"
              loading={isLoading}
              className="w-full bg-primary hover:bg-primary-hover text-white rounded-[3px] py-2.5 text-[13px] font-semibold transition-colors flex items-center justify-center gap-2"
            >
              Iniciar Sesión
              <ArrowRight className="w-3.5 h-3.5" />
            </LoadingButton>

          </form>
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
