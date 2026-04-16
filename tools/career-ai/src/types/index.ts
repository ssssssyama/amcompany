export interface WorkExperience {
  company: string;
  position: string;
  startDate: string;
  endDate: string;
  description: string;
}

export interface ResumeInput {
  name: string;
  email: string;
  phone: string;
  experiences: WorkExperience[];
  skills: string;
  qualifications: string;
  targetCompany: string;
  targetPosition: string;
  jobDescription: string;
}

export interface MotivationInput {
  experiences: WorkExperience[];
  skills: string;
  targetCompany: string;
  targetPosition: string;
  jobDescription: string;
  companyInfo: string;
}

export interface ReviewInput {
  text: string;
  type: "self_pr" | "motivation";
}

export interface GenerateRequest {
  type: "resume" | "motivation" | "review";
  input: ResumeInput | MotivationInput | ReviewInput;
}

export interface GenerateResponse {
  content: string;
  sections?: {
    title: string;
    content: string;
  }[];
}
