import { Link } from 'react-router-dom';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Radar,
  ShieldCheck,
  Cpu,
  Blocks,
  Plug,
  Lock,
  Sparkles,
  ArrowRight,
  Moon,
  Sun,
  BookOpen,
  Newspaper,
  Check,
  Building2,
} from 'lucide-react';
import Button from '@/components/ui/Button';
import Card from '@/components/ui/Card';
import env from '@/config/env';
import { getStoredTheme, isDarkTheme, setTheme } from '@/lib/theme/theme';

function useInView(options) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) setInView(true);
    }, options);
    observer.observe(el);
    return () => observer.disconnect();
  }, [options]);

  return { ref, inView };
}

function Reveal({ children, className }) {
  const { ref, inView } = useInView({ threshold: 0.15 });
  return (
    <div
      ref={ref}
      className={
        `${className || ''} transition-all duration-700 ease-out will-change-transform `
        + (inView ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4')
      }
    >
      {children}
    </div>
  );
}

function AnchorLink({ href, children }) {
  return (
    <a
      href={href}
      className="text-sm text-slate-400 hover:text-slate-200 transition-colors"
    >
      {children}
    </a>
  );
}

export default function MarketingLandingPage() {
  const [darkThemeEnabled, setDarkThemeEnabled] = useState(() => {
    const stored = getStoredTheme();
    if (stored) return stored === 'dark';
    return isDarkTheme();
  });

  const toggleTheme = () => {
    const next = !darkThemeEnabled;
    setTheme(next ? 'dark' : 'light');
    setDarkThemeEnabled(next);
  };

  const demoMailto = useMemo(() => {
    const subject = encodeURIComponent('AeroCommand — Request Demo');
    const body = encodeURIComponent(
      'Hi AeroCommand team,\n\nI would like to request a demo.\n\nCompany: \nUse case: \nFleet size: \nTimeline: \n\nThanks,'
    );
    return `mailto:${env.SUPPORT_EMAIL}?subject=${subject}&body=${body}`;
  }, []);

  const [billingCycle, setBillingCycle] = useState('monthly');
  const pricing = useMemo(() => {
    const yearly = billingCycle === 'yearly';
    return {
      starter: { price: yearly ? '$39' : '$49', suffix: yearly ? '/mo billed yearly' : '/mo' },
      pro: { price: yearly ? '$129' : '$149', suffix: yearly ? '/mo billed yearly' : '/mo' },
      enterprise: { price: 'Custom', suffix: 'pricing' },
    };
  }, [billingCycle]);

  return (
    <div className="relative min-h-screen text-slate-100 scroll-smooth">
      {/* Global Background (applies to all sections) */}
      <div className="fixed inset-0 -z-10 overflow-hidden">
        <video
          className="absolute inset-0 h-full w-full object-cover opacity-20"
          autoPlay
          muted
          loop
          playsInline
        >
          <source src="/landing/hero.mp4" type="video/mp4" />
        </video>
        <div className="absolute inset-0 bg-gradient-to-b from-slate-950/90 via-slate-950/80 to-slate-950" />
      </div>

      {/* Hero */}
      <div className="relative">

        <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
          <div className="flex items-center gap-3">
            <div className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 shadow-lg shadow-blue-500/25">
              <Radar className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight text-slate-100">AeroCommand</div>
              <div className="text-xs text-slate-400">Automated Commercial Drone Platform</div>
            </div>
          </div>

          <div className="hidden md:flex items-center gap-6">
            <AnchorLink href="#features">Features</AnchorLink>
            <AnchorLink href="#solutions">Solutions</AnchorLink>
            <AnchorLink href="#partners">Partners</AnchorLink>
            <AnchorLink href="#resources">Resources</AnchorLink>
            <AnchorLink href="#pricing">Pricing</AnchorLink>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={toggleTheme}
              aria-label={darkThemeEnabled ? 'Disable dark theme' : 'Enable dark theme'}
              className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              {darkThemeEnabled ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
            </button>
            <Link to="/login">
              <Button size="md">Sign in</Button>
            </Link>
          </div>
        </header>

        <main className="relative z-10 mx-auto max-w-6xl px-6 pb-14 pt-10">
          <Reveal>
            <div className="inline-flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/50 px-3 py-1 text-xs text-slate-300">
              <Sparkles className="h-3.5 w-3.5 text-blue-400" />
              Build, deploy, and scale autonomous drone apps
            </div>
          </Reveal>

          <Reveal className="mt-5">
            <h1 className="max-w-3xl text-4xl font-bold tracking-tight text-slate-50 sm:text-5xl">
              Build, deploy, and scale fully automated commercial drone applications from a single platform.
            </h1>
          </Reveal>

          <Reveal className="mt-4">
            <p className="max-w-2xl text-base text-slate-300 sm:text-lg">
              Automate fleets, integrate via APIs, run real-time analytics, and secure critical operations—all from a
              unified control surface.
            </p>
          </Reveal>

          <Reveal className="mt-8">
            <div className="flex flex-wrap items-center gap-3">
              <a href={demoMailto}>
                <Button size="lg" iconRight={ArrowRight}>Request demo</Button>
              </a>
              <Link to="/login">
                <Button size="lg" variant="secondary">Get started</Button>
              </Link>
              <a href="#pricing" className="text-sm text-slate-400 hover:text-slate-200 transition-colors">
                View pricing
              </a>
            </div>
          </Reveal>

          <Reveal className="mt-10">
            <div className="grid gap-4 lg:grid-cols-12">
              <div className="lg:col-span-5">
                <Card className="bg-slate-900/60">
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-slate-800 border border-slate-700/50">
                      <ShieldCheck className="h-4 w-4 text-blue-400" />
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-slate-100">Enterprise-grade control</div>
                      <div className="mt-1 text-sm text-slate-400">
                        Secure workflows, role-based access, and auditable operations for safety-critical missions.
                      </div>
                    </div>
                  </div>
                </Card>

                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <Card className="bg-slate-900/60">
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-slate-800 border border-slate-700/50">
                        <Cpu className="h-4 w-4 text-blue-400" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-slate-100">AI-R Engine</div>
                        <div className="mt-1 text-sm text-slate-400">Real-time AI analytics optimized for cost and security.</div>
                      </div>
                    </div>
                  </Card>
                  <Card className="bg-slate-900/60">
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-slate-800 border border-slate-700/50">
                        <Blocks className="h-4 w-4 text-blue-400" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-slate-100">Developer-ready</div>
                        <div className="mt-1 text-sm text-slate-400">APIs and integrations to accelerate product delivery.</div>
                      </div>
                    </div>
                  </Card>
                </div>
              </div>

              <div className="lg:col-span-7">
                <div className="grid grid-cols-2 gap-4">
                  <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/40">
                    <img
                      src="/landing/screen-1.png"
                      alt="AI control dashboard screenshot"
                      className="h-full w-full object-cover"
                      loading="lazy"
                    />
                  </div>
                  <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/40">
                    <img
                      src="/landing/screen-2.png"
                      alt="Fleet operations dashboard screenshot"
                      className="h-full w-full object-cover"
                      loading="lazy"
                    />
                  </div>
                </div>
              </div>
            </div>
          </Reveal>
        </main>
      </div>

      {/* Core Features */}
      <section id="features" className="mx-auto max-w-6xl px-6 py-14">
        <Reveal>
          <div className="flex items-end justify-between gap-6">
            <div>
              <h2 className="text-2xl font-semibold text-slate-100">Core features</h2>
              <p className="mt-2 text-slate-400">
                Everything you need to automate operations, integrate systems, and protect mission-critical data.
              </p>
            </div>
          </div>
        </Reveal>

        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Reveal>
            <Card hover className="bg-slate-900/60">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-800 border border-slate-700/50">
                  <Radar className="h-5 w-5 text-blue-400" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-slate-100">Fleet Automation</div>
                  <div className="mt-1 text-sm text-slate-400">Fully automate drone operations and manage fleets remotely.</div>
                </div>
              </div>
            </Card>
          </Reveal>
          <Reveal>
            <Card hover className="bg-slate-900/60">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-800 border border-slate-700/50">
                  <Blocks className="h-5 w-5 text-blue-400" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-slate-100">APIs</div>
                  <div className="mt-1 text-sm text-slate-400">Accelerate product development with robust developer access.</div>
                </div>
              </div>
            </Card>
          </Reveal>
          <Reveal>
            <Card hover className="bg-slate-900/60">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-800 border border-slate-700/50">
                  <Plug className="h-5 w-5 text-blue-400" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-slate-100">Flinks</div>
                  <div className="mt-1 text-sm text-slate-400">Seamless integration with third-party and custom apps.</div>
                </div>
              </div>
            </Card>
          </Reveal>
          <Reveal>
            <Card hover className="bg-slate-900/60">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-800 border border-slate-700/50">
                  <Lock className="h-5 w-5 text-blue-400" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-slate-100">Data Security</div>
                  <div className="mt-1 text-sm text-slate-400">Enterprise-grade protection and compliance controls.</div>
                </div>
              </div>
            </Card>
          </Reveal>
          <Reveal>
            <Card hover className="bg-slate-900/60">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-800 border border-slate-700/50">
                  <Cpu className="h-5 w-5 text-blue-400" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-slate-100">AI-R Engine</div>
                  <div className="mt-1 text-sm text-slate-400">Real-time AI analytics optimized for IT security and cost efficiency.</div>
                </div>
              </div>
            </Card>
          </Reveal>
        </div>
      </section>

      {/* Industry Solutions */}
      <section id="solutions" className="mx-auto max-w-6xl px-6 py-14">
        <Reveal>
          <h2 className="text-2xl font-semibold text-slate-100">Industry solutions</h2>
          <p className="mt-2 text-slate-400">Scalable use cases across security, infrastructure, and industrial operations.</p>
        </Reveal>

        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[
            { title: 'Security Services', desc: 'Autonomous patrol & intruder detection' },
            { title: 'Mining Operations', desc: 'Site progress tracking' },
            { title: 'Electric Utilities', desc: 'Fault detection & asset monitoring' },
            { title: 'Public Safety', desc: 'Rapid emergency response' },
            { title: 'Solar Operations', desc: 'Panel inspection & diagnostics' },
            { title: 'Oil & Gas', desc: 'Predictive equipment failure detection' },
            { title: 'Maritime Ports', desc: 'Port & vessel surveillance' },
            { title: 'Railroad Operations', desc: 'Continuous rail inspection' },
            { title: 'Corrections & Detention', desc: 'Contraband & perimeter monitoring' },
            { title: 'Data Centers', desc: 'Critical infrastructure security' },
            { title: 'Transport & Highways', desc: 'Corridor monitoring' },
            { title: 'Construction', desc: 'Progress & safety tracking' },
            { title: 'Agriculture', desc: 'Smart crop and land monitoring' },
          ].map((item) => (
            <Reveal key={item.title}>
              <Card hover className="bg-slate-900/60">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-800 border border-slate-700/50">
                    <Building2 className="h-5 w-5 text-blue-400" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-slate-100">{item.title}</div>
                    <div className="mt-1 text-sm text-slate-400">{item.desc}</div>
                  </div>
                </div>
              </Card>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Partners */}
      <section id="partners" className="mx-auto max-w-6xl px-6 py-14">
        <Reveal>
          <h2 className="text-2xl font-semibold text-slate-100">Partners</h2>
          <p className="mt-2 text-slate-400">Ecosystem collaboration to accelerate delivery and integration.</p>
        </Reveal>

        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          <Reveal>
            <Card hover className="bg-slate-900/60">
              <a href="https://www.makerskills.tn/" target="_blank" rel="noreferrer" className="block">
                <div className="flex items-center gap-4">
                  <div className="h-12 w-12 rounded-xl bg-slate-800 border border-slate-700/50 flex items-center justify-center overflow-hidden">
                    <img src="/landing/logos/makerskills.png" alt="Maker Skills" className="h-8 w-8 object-contain" loading="lazy" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-slate-100">Maker Skills</div>
                    <div className="mt-1 text-sm text-slate-400">Applied engineering partner helping teams ship reliable systems faster.</div>
                  </div>
                  <ArrowRight className="h-4 w-4 text-slate-500" />
                </div>
              </a>
            </Card>
          </Reveal>

          <Reveal>
            <Card className="bg-slate-900/60">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-slate-800 border border-slate-700/50">
                  <Blocks className="h-5 w-5 text-blue-400" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-slate-100">Future partners</div>
                  <div className="mt-1 text-sm text-slate-400">Space reserved for integrations, hardware vendors, and service providers.</div>
                </div>
              </div>
            </Card>
          </Reveal>
        </div>
      </section>

      {/* Resources */}
      <section id="resources" className="mx-auto max-w-6xl px-6 py-14">
        <Reveal>
          <h2 className="text-2xl font-semibold text-slate-100">Resources</h2>
          <p className="mt-2 text-slate-400">Guides for operators and developers, plus the stack behind the platform.</p>
        </Reveal>

        <div className="mt-8 grid gap-4 lg:grid-cols-12">
          <div className="lg:col-span-7 grid gap-4 sm:grid-cols-2">
            <Reveal>
              <Card hover className="bg-slate-900/60">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-800 border border-slate-700/50">
                    <Newspaper className="h-5 w-5 text-blue-400" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-slate-100">Blog / Articles</div>
                    <div className="mt-1 text-sm text-slate-400">Product updates, operations playbooks, and best practices.</div>
                  </div>
                </div>
              </Card>
            </Reveal>
            <Reveal>
              <Card hover className="bg-slate-900/60">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-800 border border-slate-700/50">
                    <BookOpen className="h-5 w-5 text-blue-400" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-slate-100">Documentation</div>
                    <div className="mt-1 text-sm text-slate-400">API reference, integration guides, and deployment notes.</div>
                  </div>
                </div>
              </Card>
            </Reveal>
          </div>

          <Reveal className="lg:col-span-5">
            <Card className="bg-slate-900/60">
              <div className="text-sm font-semibold text-slate-100">Backend technologies</div>
              <div className="mt-2 text-sm text-slate-400">
                Built with a modern stack for secure APIs and real-time operations (FastAPI, PostgreSQL,
                MQTT/EMQX, Docker, Kubernetes).
              </div>
              <div className="mt-5 grid grid-cols-2 gap-4">
                {[
                  { name: 'PostgreSQL', src: '/landing/logos/postgresql.png' },
                  { name: 'MQTT', src: '/landing/logos/mqtt.png' },
                  { name: 'EMQX', src: '/landing/logos/emqx.png' },
                  { name: 'MAVLink', src: '/landing/logos/mavlink.png' },
                ].map((t) => (
                  <div key={t.name} className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/40 p-4">
                    <div className="h-12 w-12 rounded-xl bg-slate-800 border border-slate-700/50 flex items-center justify-center overflow-hidden">
                      <img src={t.src} alt={t.name} className="h-8 w-8 object-contain" loading="lazy" />
                    </div>
                    <div className="text-sm text-slate-200">{t.name}</div>
                  </div>
                ))}
              </div>
            </Card>
          </Reveal>
        </div>
      </section>

      {/* Testimonials (optional) */}
      <section className="mx-auto max-w-6xl px-6 py-14">
        <Reveal>
          <h2 className="text-2xl font-semibold text-slate-100">Trusted for mission-critical operations</h2>
          <p className="mt-2 text-slate-400">A SaaS experience designed for reliability, speed, and clarity.</p>
        </Reveal>

        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {[{
            quote: 'We reduced response times by standardizing telemetry and alerts in one console.',
            role: 'Operations Lead',
          }, {
            quote: 'The API-first approach helped our team integrate workflows without slowing down deployments.',
            role: 'Platform Engineer',
          }, {
            quote: 'Role-based access and auditability made it easy to operate securely at scale.',
            role: 'Security Manager',
          }].map((t) => (
            <Reveal key={t.role}>
              <Card className="bg-slate-900/60">
                <div className="text-sm text-slate-300">“{t.quote}”</div>
                <div className="mt-4 text-xs text-slate-500">{t.role}</div>
              </Card>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="mx-auto max-w-6xl px-6 py-14">
        <Reveal>
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h2 className="text-2xl font-semibold text-slate-100">Pricing</h2>
              <p className="mt-2 text-slate-400">Choose a plan that scales from pilots to enterprise operations.</p>
            </div>
            <div className="inline-flex rounded-xl border border-slate-800 bg-slate-900/50 p-1">
              <button
                onClick={() => setBillingCycle('monthly')}
                className={
                  `px-3 py-1.5 text-sm rounded-lg transition-colors `
                  + (billingCycle === 'monthly' ? 'bg-slate-800 text-slate-100' : 'text-slate-400 hover:text-slate-200')
                }
              >
                Monthly
              </button>
              <button
                onClick={() => setBillingCycle('yearly')}
                className={
                  `px-3 py-1.5 text-sm rounded-lg transition-colors `
                  + (billingCycle === 'yearly' ? 'bg-slate-800 text-slate-100' : 'text-slate-400 hover:text-slate-200')
                }
              >
                Yearly
              </button>
            </div>
          </div>
        </Reveal>

        <div className="mt-8 grid gap-4 lg:grid-cols-3">
          <Reveal>
            <Card className="bg-slate-900/60">
              <div className="text-sm font-semibold text-slate-100">Starter</div>
              <div className="mt-3">
                <div className="text-3xl font-bold text-slate-50">{pricing.starter.price}</div>
                <div className="text-sm text-slate-400">{pricing.starter.suffix}</div>
              </div>
              <div className="mt-5 space-y-2">
                {[
                  'Basic fleet monitoring',
                  'Telemetry dashboards',
                  'Standard alerts',
                  'Email support',
                ].map((f) => (
                  <div key={f} className="flex items-start gap-2 text-sm text-slate-300">
                    <Check className="mt-0.5 h-4 w-4 text-emerald-400" />
                    <span>{f}</span>
                  </div>
                ))}
              </div>
              <div className="mt-6">
                <Link to="/login">
                  <Button fullWidth>Get started</Button>
                </Link>
              </div>
            </Card>
          </Reveal>

          <Reveal>
            <Card className="bg-slate-900/60 border-blue-500/20">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-slate-100">Professional</div>
                <div className="text-xs text-blue-400 border border-blue-500/20 bg-blue-600/10 px-2 py-1 rounded-full">Most popular</div>
              </div>
              <div className="mt-3">
                <div className="text-3xl font-bold text-slate-50">{pricing.pro.price}</div>
                <div className="text-sm text-slate-400">{pricing.pro.suffix}</div>
              </div>
              <div className="mt-5 space-y-2">
                {[
                  'Fleet automation workflows',
                  'API access',
                  'Integrations (Flinks)',
                  'Priority support',
                ].map((f) => (
                  <div key={f} className="flex items-start gap-2 text-sm text-slate-300">
                    <Check className="mt-0.5 h-4 w-4 text-emerald-400" />
                    <span>{f}</span>
                  </div>
                ))}
              </div>
              <div className="mt-6">
                <Link to="/login">
                  <Button fullWidth>Upgrade</Button>
                </Link>
              </div>
            </Card>
          </Reveal>

          <Reveal>
            <Card className="bg-slate-900/60">
              <div className="text-sm font-semibold text-slate-100">Enterprise</div>
              <div className="mt-3">
                <div className="text-3xl font-bold text-slate-50">{pricing.enterprise.price}</div>
                <div className="text-sm text-slate-400">{pricing.enterprise.suffix}</div>
              </div>
              <div className="mt-5 space-y-2">
                {[
                  'Advanced security & compliance',
                  'Dedicated environments',
                  'Custom AI/R analytics',
                  'SLA & enterprise onboarding',
                ].map((f) => (
                  <div key={f} className="flex items-start gap-2 text-sm text-slate-300">
                    <Check className="mt-0.5 h-4 w-4 text-emerald-400" />
                    <span>{f}</span>
                  </div>
                ))}
              </div>
              <div className="mt-6">
                <a href={demoMailto}>
                  <Button fullWidth variant="outline">Contact sales</Button>
                </a>
              </div>
            </Card>
          </Reveal>
        </div>
      </section>

      <footer className="border-t border-slate-900 bg-slate-950/50">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-10 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-sm font-semibold text-slate-200">AeroCommand</div>
            <div className="mt-1 text-xs text-slate-500">Secure, automated drone operations platform</div>
          </div>
          <div className="flex items-center gap-4">
            <a href={demoMailto} className="text-xs text-slate-400 hover:text-slate-200 transition-colors">Request demo</a>
            <Link to="/login" className="text-xs text-slate-400 hover:text-slate-200 transition-colors">Sign in</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
