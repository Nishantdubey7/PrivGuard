import { FileText, Video, Mic, Image } from "lucide-react";

export const sections = [
  {
    id: 'text',
    icon: FileText,
    title: "Text & Documents",
    description: "Redact .txt files",
    color: "from-cyan-500 to-blue-500",
    enabled: true
  },
  {
    id: 'pdf',
    icon: FileText,
    title: "PDF Files",
    description: "Redact PDF documents",
    color: "from-violet-500 to-purple-500",
    enabled: true
  },
  {
    id: 'audio',
    icon: Mic,
    title: "Audio Files",
    description: "Redact audio recordings",
    color: "from-green-500 to-emerald-500",
    enabled: true
  },
   {
    id: 'image',
    icon: Image,
    title: "Image Files",
    description: "Redact image files",
    color: "from-orange-500 to-red-500",
    enabled: true
  },
  {
    id: 'video',
    icon: Video,
    title: "Video Files",
    description: "Redact video files",
    color: "from-red-500 to-yellow-500",
    enabled: true
  }
];

export const redactionLevels = {
  1: { label: "Light", description: "Basic PII redaction with placeholder text [REDACTED]", color: "text-green-400" },
  2: { label: "Heavy", description: "Maximum security, Consistent Pseudonymization", color: "text-red-400" }
};

export const pdfRedactionLevels = {
  1: { 
    label: "Blur", 
    description: "Blur sensitive content - text and images are blurred for partial obscurity",
    color: "text-blue-400" 
  },
  2: { 
    label: "Black Box", 
    description: "Black box redaction - sensitive content replaced with solid black boxes",
    color: "text-green-400" 
  },
  3: { 
    label: "Synth Placeholder", 
    description: "Synthetic placeholder - realistic fake data generated to maintain document structure",
    color: "text-yellow-400" 
  },
  4: { 
    label: "Inpaint", 
    description: "AI inpainting - sensitive content seamlessly removed and background filled in",
    color: "text-red-400" 
  }
};

export const videoRedactionLevels = {
  1: { 
    label: "Face Redaction", 
    description: "Faces detected and redacted with solid boxes, without affecting associated PII",
    color: "text-blue-400" 
  },
  2: { 
    label: "Plate + PII Redaction", 
    description: "detects and redacts license plates along with associated PII",
    color: "text-green-400" 
  },
  3: { 
    label: "Face, Plate, and PII Redaction", 
    description: "Multi-object redaction - detects and redacts faces, license plates, and associated PII",
    color: "text-yellow-400" 
  },
  4: { 
    label: "Identity-Preserving Redaction", 
    description: "Preserves the subject’s face while intelligently redacting other faces, PII, and license plates.",
    color: "text-red-400" 
  }
};

export const imageRedactionLevels = {
  1: { 
    label: "Face Redaction", 
    description: "Faces detected and redacted with solid boxes, without affecting associated PII",
    color: "text-blue-400" 
  },
  2: { 
    label: "Plate + PII Redaction", 
    description: "detects and redacts license plates along with associated PII",
    color: "text-green-400" 
  },
  3: { 
    label: "Face, Plate, and PII Redaction", 
    description: "Multi-object redaction - detects and redacts faces, license plates, and associated PII",
    color: "text-yellow-400" 
  },
  4: { 
    label: "Identity-Preserving Redaction", 
    description: "Preserves the subject’s face while intelligently redacting other faces, PII, and license plates.",
    color: "text-red-400" 
  }
};

export const audioRedactionLevels = {
  1: { 
    label: "Beep Censoring", 
    description: "Beep tone censoring - sensitive audio replaced with beep sounds",
    color: "text-green-400" 
  },
  2: { 
    label: "Silence Gaps", 
    description: "Silence replacement - sensitive audio replaced with silent gaps",
    color: "text-yellow-400" 
  }
};