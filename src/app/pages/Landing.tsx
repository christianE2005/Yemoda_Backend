import { Link } from 'react-router';
import { 
  BarChart3, 
  Bell, 
  Brain, 
  Shield, 
  TrendingUp,
  Users,
  ArrowRight,
  Zap,
  Globe,
  GitBranch,
  Layers
} from 'lucide-react';

export default function Landing() {
  const features = [
    {
      icon: <BarChart3 className="w-5 h-5" />,
      title: 'KPIs en Tiempo Real',
      description: 'Monitoreo continuo del avance, presupuesto y métricas críticas de todos tus proyectos.'
    },
    {
      icon: <Bell className="w-5 h-5" />,
      title: 'Alertas Tempranas',
      description: 'Sistema inteligente de notificaciones para identificar riesgos antes de que impacten.'
    },
    {
      icon: <Brain className="w-5 h-5" />,
      title: 'Análisis Predictivo IA',
      description: 'Predicciones sobre probabilidad de retrasos y desviaciones presupuestales.'
    },
    {
      icon: <Shield className="w-5 h-5" />,
      title: 'Seguridad Corporativa',
      description: 'Roles y permisos granulares para proteger información sensible del negocio.'
    },
    {
      icon: <TrendingUp className="w-5 h-5" />,
      title: 'Reportes Ejecutivos',
      description: 'Dashboards personalizados con insights accionables para directivos.'
    },
    {
      icon: <Users className="w-5 h-5" />,
      title: 'Gestión Colaborativa',
      description: 'Coordinación eficiente entre equipos con visibilidad total del flujo.'
    }
  ];

  const stats = [
    { value: '99.9%', label: 'Uptime garantizado' },
    { value: '150+', label: 'Proyectos gestionados' },
    { value: '40%', label: 'Reducción de retrasos' },
    { value: '4.8/5', label: 'Satisfacción de usuarios' },
  ];

  const steps = [
    { number: '01', icon: <Layers className="w-5 h-5" />, title: 'Configura tus proyectos', description: 'Importa o crea proyectos con cronogramas, presupuestos y equipos asignados.' },
    { number: '02', icon: <GitBranch className="w-5 h-5" />, title: 'Monitorea en tiempo real', description: 'Visualiza KPIs, avance y desviaciones con dashboards actualizados automáticamente.' },
    { number: '03', icon: <Zap className="w-5 h-5" />, title: 'Actúa con inteligencia', description: 'Recibe alertas predictivas y recomendaciones basadas en análisis de datos.' },
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/80 backdrop-blur-sm sticky top-0 z-50" role="banner">
        <div className="container mx-auto px-6 h-14 flex items-center justify-between max-w-6xl">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-primary rounded-[3px] flex items-center justify-center">
              <span className="text-primary-foreground font-semibold text-xs">PI</span>
            </div>
            <span className="font-semibold text-foreground text-[13px]">Project Intelligence</span>
          </div>
          <nav className="hidden md:flex items-center gap-6" aria-label="Navegación principal">
            <a href="#features" className="text-[12px] text-muted-foreground hover:text-foreground transition-colors">Funciones</a>
            <a href="#how-it-works" className="text-[12px] text-muted-foreground hover:text-foreground transition-colors">Cómo funciona</a>
            <a href="#testimonios" className="text-[12px] text-muted-foreground hover:text-foreground transition-colors">Testimonios</a>
          </nav>
          <div className="flex items-center gap-3">
            <Link 
              to="/login" 
              className="text-[12px] text-muted-foreground hover:text-foreground transition-colors font-medium"
            >
              Iniciar sesión
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="container mx-auto px-6 pt-20 pb-16 max-w-6xl">
        <div className="max-w-3xl mx-auto text-center">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-[3px] bg-primary/10 text-primary text-[11px] font-medium mb-6">
            <Zap className="w-3 h-3" />
            Plataforma empresarial · ABCDH Technologies
          </div>

          <h1 className="text-4xl md:text-5xl lg:text-[3.5rem] font-semibold text-foreground mb-5 leading-[1.15] tracking-tight">
            Gestión Inteligente de{' '}
            <span className="text-primary">Proyectos</span>
          </h1>
          
          <p className="text-base md:text-lg text-muted-foreground mb-8 max-w-xl mx-auto leading-relaxed">
            Centraliza el portafolio de proyectos de ABCDH Technologies, monitorea KPIs en tiempo real y toma decisiones basadas en análisis predictivo.
          </p>

          <div className="flex items-center gap-3 justify-center mb-6">
            <Link 
              to="/login"
              className="px-6 py-2.5 bg-primary hover:bg-primary-hover text-primary-foreground rounded-[3px] text-[13px] font-medium transition-colors inline-flex items-center gap-2"
            >
              Acceder a la plataforma
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>


        </div>

        {/* Hero Dashboard Preview */}
        <div className="mt-14 max-w-4xl mx-auto">
          <div className="rounded-[4px] border border-border bg-card p-1.5 shadow-sm">
            <div className="bg-secondary/60 rounded-[4px] overflow-hidden">
              {/* Mock browser bar */}
              <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-border/50 bg-card/60">
                <div className="w-2.5 h-2.5 rounded-full bg-destructive/40" />
                <div className="w-2.5 h-2.5 rounded-full bg-warning/40" />
                <div className="w-2.5 h-2.5 rounded-full bg-success/40" />
                <div className="flex-1 ml-3">
                  <div className="max-w-xs mx-auto bg-background/70 rounded px-3 py-1 text-[10px] text-muted-foreground text-center">
                    pi.abcdhtechnologies.com/dashboard
                  </div>
                </div>
              </div>
              {/* Mock dashboard content */}
              <div className="p-5 space-y-4">
                {/* Mock KPI cards */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { label: 'Avance', value: '62%', trend: '+4.3%', color: 'text-success' },
                    { label: 'Presupuesto', value: '79%', trend: '+3.8%', color: 'text-success' },
                    { label: 'En Riesgo', value: '3', trend: '+1', color: 'text-warning' },
                    { label: 'Desviación', value: '-3.2%', trend: '±1.5%', color: 'text-muted-foreground' },
                  ].map((kpi, i) => (
                    <div key={i} className="bg-card rounded-[4px] border border-border/60 p-3">
                      <p className="text-[9px] uppercase tracking-wider text-muted-foreground mb-1">{kpi.label}</p>
                      <p className="text-lg font-semibold text-foreground">{kpi.value}</p>
                      <p className={`text-[9px] ${kpi.color}`}>{kpi.trend}</p>
                    </div>
                  ))}
                </div>
                {/* Mock chart area */}
                <div className="bg-card rounded-[4px] border border-border/60 p-4 h-24 sm:h-32 flex items-end gap-1">
                  {[40, 55, 50, 62, 58, 70, 65, 75, 72, 80, 78, 85].map((h, i) => (
                    <div
                      key={i}
                      className="flex-1 bg-primary/20 rounded-t"
                      style={{ height: `${h}%` }}
                    >
                      <div className="w-full bg-primary/60 rounded-t" style={{ height: '60%' }} />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Bar */}
      <section className="border-y border-border bg-card/50">
        <div className="container mx-auto px-6 py-10 max-w-6xl">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {stats.map((stat, i) => (
              <div key={i} className="text-center">
                <p className="text-2xl font-semibold text-foreground mb-1">{stat.value}</p>
                <p className="text-xs text-muted-foreground">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="container mx-auto px-6 py-20 max-w-6xl scroll-mt-13">
        <div className="text-center mb-14">
          <p className="text-xs font-medium text-primary uppercase tracking-wider mb-2">Funciones</p>
          <h2 className="text-2xl md:text-3xl font-semibold text-foreground mb-3">
            Todo para gestionar proyectos complejos
          </h2>
          <p className="text-sm text-muted-foreground max-w-lg mx-auto">
            Herramientas de nivel empresarial diseñadas para equipos de ABCDH Technologies
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4 max-w-5xl mx-auto">
          {features.map((feature, index) => (
            <div
              key={index}
              className="bg-card border border-border rounded-[4px] p-4 hover:border-primary/30 transition-colors group"
            >
              <div className="w-9 h-9 bg-primary/10 rounded-[3px] flex items-center justify-center text-primary mb-3 group-hover:bg-primary/15 transition-colors">
                {feature.icon}
              </div>
              <h3 className="text-[12px] font-semibold text-foreground mb-1.5">{feature.title}</h3>
              <p className="text-[11px] text-muted-foreground leading-relaxed">{feature.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="bg-card/50 border-y border-border scroll-mt-25">
        <div className="container mx-auto px-6 py-20 max-w-6xl">
          <div className="text-center mb-14">
            <p className="text-xs font-medium text-primary uppercase tracking-wider mb-2">Proceso</p>
            <h2 className="text-2xl md:text-3xl font-semibold text-foreground mb-3">
              Comienza en 3 pasos
            </h2>
            <p className="text-sm text-muted-foreground max-w-md mx-auto">
              De la configuración a la inteligencia accionable en minutos
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8 max-w-4xl mx-auto">
            {steps.map((step, index) => (
              <div key={index} className="relative text-center">
                <div className="w-11 h-11 rounded-[4px] bg-primary/10 flex items-center justify-center text-primary mx-auto mb-4">
                  {step.icon}
                </div>
                <span className="text-[10px] font-semibold text-primary uppercase tracking-widest">{step.number}</span>
                <h3 className="text-sm font-semibold text-foreground mt-1 mb-2">{step.title}</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">{step.description}</p>
                {index < steps.length - 1 && (
                  <div className="hidden md:block absolute top-6 left-[60%] w-[80%] border-t border-dashed border-border" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Social Proof / Testimonial */}
      <section id="testimonios" className="container mx-auto px-6 py-20 max-w-6xl scroll-mt-13">
        <div className="max-w-3xl mx-auto text-center">
          <Globe className="w-8 h-8 text-primary/40 mx-auto mb-6" />
          <blockquote className="text-lg md:text-xl font-medium text-foreground leading-relaxed mb-6 italic">
            "Project Intelligence nos permitió reducir los retrasos en un 40% y tener visibilidad completa
            del portafolio de proyectos. La toma de decisiones ahora es basada en datos reales."
          </blockquote>
          <div className="flex items-center justify-center gap-3">
            <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center">
              <span className="text-primary text-sm font-semibold">MG</span>
            </div>
            <div className="text-left">
              <p className="text-sm font-medium text-foreground">María González</p>
              <p className="text-xs text-muted-foreground">VP de Operaciones, ABCDH Technologies</p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="container mx-auto px-6 pb-20 max-w-6xl">
        <div className="bg-card border border-border rounded-[4px] p-8 md:p-12 text-center max-w-3xl mx-auto relative overflow-hidden">
          <div className="absolute inset-0 bg-primary/[0.02]" />
          <div className="relative">
            <h2 className="text-xl md:text-2xl font-semibold text-foreground mb-3">
              ¿Listo para transformar tu gestión de proyectos?
            </h2>
            <p className="text-sm text-muted-foreground mb-8 max-w-md mx-auto">
              Descubre cómo Project Intelligence potencia la gestión de proyectos en ABCDH Technologies.
            </p>
            <div className="flex items-center gap-3 justify-center">
              <Link 
                to="/login"
                className="inline-flex items-center gap-2 px-6 py-2.5 bg-primary hover:bg-primary-hover text-primary-foreground rounded-[3px] text-[13px] font-medium transition-colors"
              >
                Acceder a la plataforma
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link 
                to="/login"
                className="inline-flex items-center gap-2 px-6 py-2.5 bg-secondary hover:bg-accent text-foreground rounded-[3px] text-[13px] font-medium transition-colors"
              >
                Iniciar sesión
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border" role="contentinfo">
        <div className="container mx-auto px-6 py-8 max-w-6xl">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2.5">
              <div className="w-6 h-6 bg-primary rounded-[3px] flex items-center justify-center">
                <span className="text-primary-foreground font-semibold text-[10px]">PI</span>
              </div>
              <span className="text-[13px] font-medium text-foreground">Project Intelligence</span>
            </div>
            <div className="flex items-center gap-6">
              <a href="#" className="text-xs text-muted-foreground hover:text-foreground transition-colors">Términos</a>
              <a href="#" className="text-xs text-muted-foreground hover:text-foreground transition-colors">Privacidad</a>
              <a href="#" className="text-xs text-muted-foreground hover:text-foreground transition-colors">Contacto</a>
            </div>
            <p className="text-xs text-muted-foreground">
              &copy; 2026 ABCDH Technologies. Todos los derechos reservados.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}