/**
 * Common ICD-10 Diagnostic Codes for primary care, emergency, and hospital ward encounters.
 * Grounded in WHO ICD-10-CM international classification.
 */

export interface Icd10Option {
  value: string;
  label: string;
  category: string;
}

export const COMMON_ICD10_CODES: Icd10Option[] = [
  // Infectious & Parasitic Diseases
  { value: "B54",   label: "B54 — Malaria, unspecified", category: "Infectious" },
  { value: "A01.0", label: "A01.0 — Typhoid fever", category: "Infectious" },
  { value: "A09",   label: "A09 — Infectious gastroenteritis and colitis", category: "Infectious" },
  { value: "A15.0", label: "A15.0 — Tuberculosis of lung", category: "Infectious" },
  { value: "B20",   label: "B20 — Human immunodeficiency virus [HIV] disease", category: "Infectious" },
  { value: "B18.2", label: "B18.2 — Chronic viral hepatitis C", category: "Infectious" },
  { value: "A00.9", label: "A00.9 — Cholera, unspecified", category: "Infectious" },

  // Respiratory System
  { value: "J00",   label: "J00 — Acute nasopharyngitis [common cold]", category: "Respiratory" },
  { value: "J06.9", label: "J06.9 — Acute upper respiratory infection, unspecified", category: "Respiratory" },
  { value: "J18.9", label: "J18.9 — Pneumonia, unspecified organism", category: "Respiratory" },
  { value: "J20.9", label: "J20.9 — Acute bronchitis, unspecified", category: "Respiratory" },
  { value: "J45.9", label: "J45.9 — Asthma, unspecified", category: "Respiratory" },
  { value: "J44.9", label: "J44.9 — Chronic obstructive pulmonary disease, unspecified", category: "Respiratory" },

  // Circulatory & Cardiovascular
  { value: "I10",   label: "I10 — Essential (primary) hypertension", category: "Cardiovascular" },
  { value: "I21.9", label: "I21.9 — Acute myocardial infarction, unspecified", category: "Cardiovascular" },
  { value: "I25.1", label: "I25.1 — Atherosclerotic heart disease", category: "Cardiovascular" },
  { value: "I50.9", label: "I50.9 — Heart failure, unspecified", category: "Cardiovascular" },
  { value: "I64",   label: "I64 — Stroke, not specified as haemorrhage or infarction", category: "Cardiovascular" },

  // Endocrine, Nutritional & Metabolic
  { value: "E11.9", label: "E11.9 — Type 2 diabetes mellitus without complications", category: "Endocrine" },
  { value: "E10.9", label: "E10.9 — Type 1 diabetes mellitus without complications", category: "Endocrine" },
  { value: "E66.9", label: "E66.9 — Obesity, unspecified", category: "Endocrine" },
  { value: "E03.9", label: "E03.9 — Hypothyroidism, unspecified", category: "Endocrine" },

  // Digestive System
  { value: "K29.7", label: "K29.7 — Gastritis, unspecified", category: "Gastrointestinal" },
  { value: "K21.9", label: "K21.9 — Gastro-oesophageal reflux disease", category: "Gastrointestinal" },
  { value: "K35.8", label: "K35.8 — Acute appendicitis, other and unspecified", category: "Gastrointestinal" },
  { value: "K40.9", label: "K40.9 — Unilateral inguinal hernia", category: "Gastrointestinal" },

  // Genitourinary & Maternal
  { value: "N39.0", label: "N39.0 — Urinary tract infection, site not specified", category: "Genitourinary" },
  { value: "N18.9", label: "N18.9 — Chronic kidney disease, unspecified", category: "Genitourinary" },
  { value: "O80",   label: "O80 — Single spontaneous delivery", category: "Maternal" },
  { value: "Z34.9", label: "Z34.9 — Supervision of normal pregnancy, unspecified", category: "Maternal" },

  // Musculoskeletal & Trauma / Injury
  { value: "M54.5", label: "M54.5 — Low back pain", category: "Musculoskeletal" },
  { value: "M19.9", label: "M19.9 — Osteoarthritis, unspecified site", category: "Musculoskeletal" },
  { value: "S72.0", label: "S72.0 — Fracture of head and neck of femur", category: "Injury" },
  { value: "S06.0", label: "S06.0 — Concussion", category: "Injury" },
  { value: "T14.9", label: "T14.9 — Injury, unspecified", category: "Injury" },

  // Mental & Behavioral
  { value: "F32.9", label: "F32.9 — Major depressive disorder, single episode, unspecified", category: "Mental Health" },
  { value: "F41.9", label: "F41.9 — Anxiety disorder, unspecified", category: "Mental Health" },
  { value: "F10.2", label: "F10.2 — Alcohol dependence syndrome", category: "Mental Health" },

  // General Symptoms & Signs
  { value: "R50.9", label: "R50.9 — Fever, unspecified", category: "Symptoms" },
  { value: "R51",   label: "R51 — Headache", category: "Symptoms" },
  { value: "R05",   label: "R05 — Cough", category: "Symptoms" },
  { value: "R10.9", label: "R10.9 — Abdominal pain, unspecified", category: "Symptoms" },
];
