'use client';

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function ComingSoonSection({ section }) {
  const Icon = section.icon;

  return (
    <Card className="bg-white/[0.02] border-white/5 backdrop-blur-sm max-w-2xl mx-auto">
      <CardContent className="py-24 text-center">
        <div className={`inline-flex p-6 rounded-2xl bg-gradient-to-br ${section.color} mb-6 opacity-50`}>
          <Icon className="w-12 h-12 text-white" />
        </div>
        <h3 className="text-3xl font-bold text-white mb-3">
          {section.title}
        </h3>
        <p className="text-xl text-gray-400 mb-8">
          This feature is currently under development
        </p>
        <Badge className="bg-white/5 text-gray-500 border-0 px-6 py-2">
          Coming Soon
        </Badge>
      </CardContent>
    </Card>
  );
}