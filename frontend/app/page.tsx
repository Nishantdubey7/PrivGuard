'use client';

import { Shield, FileText, Image as ImageIcon, Video, Mic, CheckCircle2, Lock, Zap, Globe, ArrowRight } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useSession, signIn, signOut } from "next-auth/react"

export default function Home() {
  const [hoveredFeature, setHoveredFeature] = useState(null);
   const { data: session } = useSession()


  const handleTrial = () => {
      if (!session) {
        signIn();
      } else {
        window.location.href = '/dash';
      }
    }


  const features = [
    {
      icon: FileText,
      title: "Text & Documents",
      description: "Redact sensitive information from text files, PDFs, and documents instantly",
      color: "from-cyan-500 to-blue-500"
    },
    {
      icon: ImageIcon,
      title: "Image Redaction",
      description: "Automatically detect and redact PII from images and scanned documents",
      color: "from-violet-500 to-purple-500"
    },
    {
      icon: Video,
      title: "Video Processing",
      description: "Blur faces, license plates, and sensitive data in video content",
      color: "from-orange-500 to-red-500"
    },
    {
      icon: Mic,
      title: "Audio Filtering",
      description: "Remove or bleep sensitive information from audio recordings",
      color: "from-green-500 to-emerald-500"
    }
  ];

  const dataTypes = [
    "Names & Addresses", "Phone Numbers", "Email Addresses", 
    "Credit/Debit Cards", "Bank Account Details", "PAN & Aadhar Numbers",
    "Medical Records", "Blood Group", "ATM Pins", "SSN & Tax IDs"
  ];

  const useCases = [
    {
      title: "Enterprise AI",
      subtitle: "OpenAI, Anthropic & more",
      description: "Protect training data and user inputs"
    },
    {
      title: "Software Companies",
      subtitle: "SaaS & Startups",
      description: "Secure customer data in logs and analytics"
    },
    {
      title: "Cybersecurity Firms",
      subtitle: "Security Operations",
      description: "Anonymize threat intelligence and reports"
    },
    {
      title: "Healthcare",
      subtitle: "HIPAA Compliance",
      description: "HIPAA-compliant patient data redaction"
    },
    {
      title: "Legal Services",
      subtitle: "Law Firms",
      description: "Redact confidential case documents"
    },
    {
      title: "Financial Services",
      subtitle: "Banking & Fintech",
      description: "Protect customer financial information"
    }
  ];

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white overflow-hidden">
      {/* Animated background */}
      <div className="fixed inset-0 opacity-30">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-cyan-500/20 rounded-full blur-[128px] animate-pulse"></div>
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-violet-500/20 rounded-full blur-[128px] animate-pulse" style={{ animationDelay: '1s' }}></div>
        <div className="absolute top-1/2 left-1/2 w-96 h-96 bg-orange-500/10 rounded-full blur-[128px] animate-pulse" style={{ animationDelay: '2s' }}></div>
      </div>

      {/* Noise texture overlay */}
      <div className="fixed inset-0 opacity-[0.015] pointer-events-none" style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
      }}></div>

      <div className="relative z-10">
        {/* Navigation */}
        <nav className="border-b border-white/5 backdrop-blur-xl bg-black/20">
          <div className="max-w-7xl mx-auto px-6 py-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="relative">
                  <div className="absolute inset-0 bg-gradient-to-br from-cyan-400 to-violet-600 rounded-xl blur-lg opacity-50"></div>
                  <div className="relative bg-gradient-to-br from-cyan-500 to-violet-600 p-2.5 rounded-xl">
                    <Shield className="w-6 h-6 text-white" strokeWidth={2.5} />
                  </div>
                </div>
                <span className="text-2xl font-bold bg-gradient-to-r from-cyan-400 via-violet-400 to-orange-400 bg-clip-text text-transparent">
                  PrivGuard
                </span>
              </div>
              <div className="hidden md:flex items-center gap-8">
                <a href="#features" className="text-gray-300 hover:text-white transition-colors text-sm font-medium">Features</a>
                <a href="#use-cases" className="text-gray-300 hover:text-white transition-colors text-sm font-medium">Use Cases</a>
                <a href="#pricing" className="text-gray-300 hover:text-white transition-colors text-sm font-medium">Pricing</a>
                <Button onClick={session ? () => signOut() : () => signIn()} className="bg-gradient-to-r from-cyan-500 to-violet-600 hover:from-cyan-400 hover:to-violet-500 text-white border-0 shadow-lg shadow-violet-500/20 hover:shadow-violet-500/40 transition-all duration-300">
                  {session ? "Sign Out" : "Sign In"}
                </Button>
              </div>
            </div>
          </div>
        </nav>

        {/* Hero Section */}
        <section className="max-w-7xl mx-auto px-6 pt-24 pb-32">
          <div className="text-center max-w-4xl mx-auto">
            <Badge variant="outline" className="inline-flex items-center gap-2 px-4 py-2 mb-8 bg-white/5 border-white/10 text-gray-300 hover:bg-white/10 backdrop-blur-sm">
              <Lock className="w-4 h-4 text-cyan-400" />
              Enterprise-Grade Data Protection
            </Badge>
            
            <h1 className="text-4xl md:text-5xl lg:text-7xl font-black mb-8 leading-[1.1] animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
              <span className="bg-gradient-to-r from-white via-gray-100 to-gray-300 bg-clip-text text-transparent">
                Redact Sensitive Data
              </span>
              <br />
              <span className="bg-gradient-to-r from-cyan-400 via-violet-400 to-orange-400 bg-clip-text text-transparent">
                Across All Platforms
              </span>
            </h1>
            
            <p className="text-xl md:text-2xl text-gray-400 mb-12 max-w-3xl mx-auto leading-relaxed animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
              Multi-platform redaction tool for enterprises, software businesses, and cybersecurity industries. 
              Protect PII in text, PDFs, images, videos, and audio.
            </p>
            
            <div className="flex flex-col sm:flex-row gap-4 justify-center items-center animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
              <Button onClick={handleTrial} size="lg" className="group bg-gradient-to-r from-cyan-500 to-violet-600 hover:from-cyan-400 hover:to-violet-500 text-white border-0 text-lg px-8 py-6 shadow-2xl shadow-violet-500/30 hover:shadow-violet-500/50 transition-all duration-300 hover:scale-105 w-full sm:w-auto">
                {!session ? "Start Free Trial" : "Go to Dashboard"}
                <ArrowRight className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" />
              </Button>
              <Button size="lg" variant="outline" className="text-lg px-8 py-6 bg-white/5 border-white/10 hover:bg-white/10 text-white backdrop-blur-sm w-full sm:w-auto">
                Watch Demo
              </Button>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-8 max-w-2xl mx-auto mt-20 animate-fade-in-up" style={{ animationDelay: '0.4s' }}>
              <div className="text-center">
                <div className="text-4xl font-black bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text text-transparent mb-2">99.9%</div>
                <div className="text-sm text-gray-500">Accuracy Rate</div>
              </div>
              <div className="text-center">
                <div className="text-4xl font-black bg-gradient-to-r from-violet-400 to-orange-400 bg-clip-text text-transparent mb-2">10M+</div>
                <div className="text-sm text-gray-500">Files Processed</div>
              </div>
              <div className="text-center">
                <div className="text-4xl font-black bg-gradient-to-r from-orange-400 to-cyan-400 bg-clip-text text-transparent mb-2">500+</div>
                <div className="text-sm text-gray-500">Enterprise Clients</div>
              </div>
            </div>
          </div>
        </section>

        {/* Features Grid */}
        <section id="features" className="max-w-7xl mx-auto px-6 py-24">
          <div className="text-center mb-16">
            <h2 className="text-5xl font-black mb-4 bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
              Multi-Platform Redaction
            </h2>
            <p className="text-xl text-gray-400">One tool. Every format. Complete protection.</p>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            {features.map((feature, index) => {
              const Icon = feature.icon;
              return (
                <Card
                  key={index}
                  onMouseEnter={() => setHoveredFeature(index)}
                  onMouseLeave={() => setHoveredFeature(null)}
                  className="group relative bg-white/[0.02] border-white/5 hover:border-white/10 backdrop-blur-sm transition-all duration-500 hover:scale-[1.02] cursor-pointer overflow-hidden"
                >
                  {/* Gradient background on hover */}
                  <div className={`absolute inset-0 bg-gradient-to-br ${feature.color} opacity-0 group-hover:opacity-5 transition-opacity duration-500`}></div>
                  
                  <CardHeader>
                    <div className={`inline-flex p-4 rounded-2xl bg-gradient-to-br ${feature.color} mb-4 w-fit group-hover:scale-110 transition-transform duration-500`}>
                      <Icon className="w-7 h-7 text-white" strokeWidth={2.5} />
                    </div>
                    <CardTitle className="text-2xl text-white group-hover:text-transparent group-hover:bg-gradient-to-r group-hover:from-white group-hover:to-gray-300 group-hover:bg-clip-text transition-all duration-300">
                      {feature.title}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <CardDescription className="text-gray-400 text-base leading-relaxed">
                      {feature.description}
                    </CardDescription>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </section>

        {/* Protected Data Types */}
        <section className="max-w-7xl mx-auto px-6 py-24">
          <div className="text-center mb-16">
            <h2 className="text-5xl font-black mb-4 bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
              What We Protect
            </h2>
            <p className="text-xl text-gray-400">Comprehensive PII detection and redaction</p>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
            {dataTypes.map((type, index) => (
              <Card
                key={index}
                className="group bg-white/[0.02] border-white/5 hover:border-cyan-500/30 hover:bg-white/[0.05] transition-all duration-300 text-center backdrop-blur-sm"
              >
                <CardContent className="p-5">
                  <CheckCircle2 className="w-6 h-6 text-cyan-400 mx-auto mb-3 group-hover:scale-110 transition-transform" />
                  <div className="text-sm font-semibold text-gray-300 group-hover:text-white transition-colors">
                    {type}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        {/* Use Cases */}
        <section id="use-cases" className="max-w-7xl mx-auto px-6 py-24">
          <div className="text-center mb-16">
            <h2 className="text-5xl font-black mb-4 bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
              Built For Your Industry
            </h2>
            <p className="text-xl text-gray-400">Trusted by leading organizations worldwide</p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {useCases.map((useCase, index) => (
              <Card
                key={index}
                className="group bg-gradient-to-br from-white/[0.03] to-white/[0.01] border-white/5 hover:border-white/10 backdrop-blur-sm transition-all duration-500 hover:scale-[1.02] hover:shadow-2xl hover:shadow-violet-500/10"
              >
                <CardHeader>
                  <div className="flex items-start gap-4">
                    <div className="p-2 rounded-xl bg-gradient-to-br from-cyan-500/10 to-violet-600/10 border border-cyan-500/20">
                      <Globe className="w-5 h-5 text-cyan-400" />
                    </div>
                    <div className="flex-1">
                      <CardTitle className="text-xl text-white mb-1">{useCase.title}</CardTitle>
                      {useCase.subtitle && (
                        <Badge variant="secondary" className="text-xs bg-white/5 text-gray-500 hover:bg-white/10 border-0">
                          {useCase.subtitle}
                        </Badge>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-gray-400 leading-relaxed">
                    {useCase.description}
                  </CardDescription>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        {/* CTA Section */}
        <section className="max-w-7xl mx-auto px-6 py-24">
          <Card className="relative overflow-hidden border-0 bg-gradient-to-r from-cyan-500 via-violet-600 to-orange-500">
            {/* Grid pattern overlay */}
            <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGRlZnM+PHBhdHRlcm4gaWQ9ImdyaWQiIHdpZHRoPSI2MCIgaGVpZ2h0PSI2MCIgcGF0dGVyblVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHBhdGggZD0iTSAxMCAwIEwgMCAwIDAgMTAiIGZpbGw9Im5vbmUiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMC41IiBvcGFjaXR5PSIwLjEiLz48L3BhdHRlcm4+PC9kZWZzPjxyZWN0IHdpZHRoPSIxMDAlIiBoZWlnaHQ9IjEwMCUiIGZpbGw9InVybCgjZ3JpZCkiLz48L3N2Zz4=')] opacity-20"></div>
            
            <CardContent className="relative z-10 text-center py-20 px-8">
              <Badge variant="secondary" className="inline-flex items-center gap-2 px-4 py-2 mb-8 bg-white/10 backdrop-blur-sm border-white/20 text-white hover:bg-white/20">
                <Zap className="w-4 h-4" />
                Start Protecting Your Data Today
              </Badge>
              
              <h2 className="text-5xl md:text-6xl font-black mb-6 text-white">
                Ready to Get Started?
              </h2>
              <p className="text-xl text-white/80 mb-10 max-w-2xl mx-auto">
                Join hundreds of enterprises protecting sensitive data with PrivGuard. 
                Start your free trial today, no credit card required.
              </p>
              
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Button size="lg" className="bg-white text-gray-900 hover:bg-gray-100 text-lg px-8 py-6 shadow-2xl hover:scale-105 transition-all duration-300">
                  Start Free Trial
                </Button>
                <Button size="lg" variant="outline" className="bg-white/10 border-2 border-white/30 text-white hover:bg-white/20 backdrop-blur-sm text-lg px-8 py-6">
                  Schedule Demo
                </Button>
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Footer */}
        <footer className="border-t border-white/5 mt-24">
          <div className="max-w-7xl mx-auto px-6 py-12">
            <div className="grid md:grid-cols-4 gap-8 mb-12">
              <div>
                <div className="flex items-center gap-3 mb-4">
                  <div className="bg-gradient-to-br from-cyan-500 to-violet-600 p-2 rounded-xl">
                    <Shield className="w-5 h-5 text-white" />
                  </div>
                  <span className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text text-transparent">
                    PrivGuard
                  </span>
                </div>
                <p className="text-gray-500 text-sm">
                  Enterprise-grade data redaction for the modern world.
                </p>
              </div>
              
              <div>
                <h4 className="font-bold text-white mb-4">Product</h4>
                <ul className="space-y-2 text-sm">
                  <li><a href="#" className="text-gray-400 hover:text-white transition-colors">Features</a></li>
                  <li><a href="#" className="text-gray-400 hover:text-white transition-colors">Pricing</a></li>
                  <li><a href="#" className="text-gray-400 hover:text-white transition-colors">API Docs</a></li>
                  <li><a href="#" className="text-gray-400 hover:text-white transition-colors">Integrations</a></li>
                </ul>
              </div>
              
              <div>
                <h4 className="font-bold text-white mb-4">Company</h4>
                <ul className="space-y-2 text-sm">
                  <li><a href="#" className="text-gray-400 hover:text-white transition-colors">About</a></li>
                  <li><a href="#" className="text-gray-400 hover:text-white transition-colors">Blog</a></li>
                  <li><a href="#" className="text-gray-400 hover:text-white transition-colors">Careers</a></li>
                  <li><a href="#" className="text-gray-400 hover:text-white transition-colors">Contact</a></li>
                </ul>
              </div>
              
              <div>
                <h4 className="font-bold text-white mb-4">Legal</h4>
                <ul className="space-y-2 text-sm">
                  <li><a href="#" className="text-gray-400 hover:text-white transition-colors">Privacy Policy</a></li>
                  <li><a href="#" className="text-gray-400 hover:text-white transition-colors">Terms of Service</a></li>
                  <li><a href="#" className="text-gray-400 hover:text-white transition-colors">Security</a></li>
                  <li><a href="#" className="text-gray-400 hover:text-white transition-colors">Compliance</a></li>
                </ul>
              </div>
            </div>
            
            <div className="pt-8 border-t border-white/5 text-center text-sm text-gray-500">
              © 2024 PrivGuard. All rights reserved.
            </div>
          </div>
        </footer>
      </div>

      <style jsx>{`
        @keyframes fade-in {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }

        @keyframes fade-in-up {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .animate-fade-in {
          animation: fade-in 0.6s ease-out forwards;
        }

        .animate-fade-in-up {
          animation: fade-in-up 0.8s ease-out forwards;
        }
      `}</style>
    </div>
  );
}