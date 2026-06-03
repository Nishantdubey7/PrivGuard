'use client';

import { useState } from "react";
import { useSession } from "next-auth/react";
import DashboardLayout from "@/components/dashboard/dashboardLayout";
import DashboardHeader from "@/components/dashboard/dashboardHeader";
import SectionSelector from "@/components/dashboard/sectionSelector";
import TextRedactionSection from "@/components/dashboard/sections/textSection";
import PdfRedactionSection from "@/components/dashboard/sections/pdfSection";
import ComingSoonSection from "@/components/dashboard/sections/comingSoonSection";
import AudioRedactionSection from "@/components/dashboard/sections/audioSection";
import VideoRedactionSection from "@/components/dashboard/sections/videoSection";
import ImageRedactionSection from "@/components/dashboard/sections/imageSection";
import { sections } from "@/lib/constants/sections";

export default function Dashboard() {
  const [activeSection, setActiveSection] = useState('text');
  const { data } = useSession();

  const currentSection = sections.find(s => s.id === activeSection);

  const renderSection = () => {
    switch (activeSection) {
      case 'text':
        return <TextRedactionSection />;
      case 'pdf':
        return <PdfRedactionSection />;
      case 'audio':
        return <AudioRedactionSection />;
      case 'video':
        return <VideoRedactionSection />;
      case 'image':
        return <ImageRedactionSection />;
      default:
        return null;
    }
  };

  return (
    <DashboardLayout>
      <DashboardHeader userName={data?.user?.name} />
      
      <SectionSelector
        sections={sections}
        activeSection={activeSection}
        onSectionChange={setActiveSection}
      />

      <section className="max-w-7xl mx-auto px-6 py-8 pb-24">
        {renderSection()}
      </section>
    </DashboardLayout>
  );
}