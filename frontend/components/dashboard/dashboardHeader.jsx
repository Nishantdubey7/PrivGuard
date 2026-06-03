'use client';

import { Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export default function DashboardHeader({ userName }) {
  return (
    <section className="max-w-7xl mx-auto px-6 pt-12 pb-8">
      <div className="text-center">
        <Badge variant="outline" className="inline-flex items-center gap-2 px-4 py-2 mb-6 bg-white/5 border-white/10 text-gray-300 backdrop-blur-sm">
          <Zap className="w-4 h-4 text-cyan-400" />
          Redaction Dashboard
        </Badge>
        <h1 className="text-5xl md:text-6xl font-black mb-4 bg-gradient-to-r from-white via-gray-100 to-gray-300 bg-clip-text text-transparent">
          {userName ? `Welcome, ${userName}!` : "Welcome to Your Dashboard!"}
        </h1>
        <p className="text-xl text-gray-400 max-w-2xl mx-auto">
          Select a file type below to begin redacting sensitive information
        </p>
      </div>
    </section>
  );
}