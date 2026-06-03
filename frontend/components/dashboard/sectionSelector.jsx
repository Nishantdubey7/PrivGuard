'use client';

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function SectionSelector({ sections, activeSection, onSectionChange }) {
  return (
    <section className="max-w-7xl mx-auto px-6 py-8">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {sections.map((section) => {
          const Icon = section.icon;
          const isActive = activeSection === section.id;
          
          return (
            <Card
              key={section.id}
              onClick={() => section.enabled && onSectionChange(section.id)}
              className={`group relative cursor-pointer transition-all duration-300 overflow-hidden ${
                isActive 
                  ? 'bg-white/[0.08] border-white/20 scale-105' 
                  : section.enabled 
                    ? 'bg-white/[0.02] border-white/5 hover:border-white/10 hover:bg-white/[0.05]'
                    : 'bg-white/[0.01] border-white/5 opacity-40 cursor-not-allowed'
              }`}
            >
              {isActive && (
                <div className={`absolute inset-0 bg-gradient-to-br ${section.color} opacity-10`}></div>
              )}
              
              <CardContent className="relative p-6 text-center">
                <div className={`inline-flex p-3 rounded-xl bg-gradient-to-br ${section.color} mb-3 ${
                  isActive ? 'scale-110' : 'group-hover:scale-105'
                } transition-transform`}>
                  <Icon className="w-6 h-6 text-white" strokeWidth={2.5} />
                </div>
                <h3 className="font-bold text-white mb-1">{section.title}</h3>
                <p className="text-sm text-gray-500">{section.description}</p>
                {!section.enabled && (
                  <Badge className="mt-2 bg-white/5 text-gray-500 border-0 text-xs">
                    Under Development
                  </Badge>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </section>
  );
}