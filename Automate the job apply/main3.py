import os
import csv
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from fpdf import FPDF
from pypdf import PdfReader

# Configuration for Local Ollama Instance
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:3b"  # Runs cool, excellent JSON generation
CSV_TRACKER_FILE = "job_tracker.csv"
INPUT_RESUME_PDF = "Saikiran_Gande.pdf"  # Place your baseline resume PDF here

# ---------------------------------------------------------------------------
# STAGE 0: Read Local PDF Resume Text & Check Existing Jobs
# ---------------------------------------------------------------------------
def extract_text_from_pdf(pdf_path):
    """
    Reads a local PDF file and extracts all plain text content.
    """
    print(f"📖 Ingesting baseline resume: {pdf_path}...")
    if not os.path.exists(pdf_path):
        print(f"❌ Error: Baseline file '{pdf_path}' not found!")
        print("Please place your 'my_resume.pdf' in this directory or update INPUT_RESUME_PDF.")
        return None
        
    try:
        reader = PdfReader(pdf_path)
        extracted_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"
        print("✅ Baseline resume text parsed successfully.")
        return extracted_text.strip()
    except Exception as e:
        print(f"❌ Failed to parse PDF text: {e}")
        return None

def get_already_processed_job_ids(file_path=CSV_TRACKER_FILE):
    """
    Reads the tracking CSV and collects all Job IDs that have already been handled.
    """
    processed_ids = set()
    if not os.path.exists(file_path):
        return processed_ids
        
    try:
        with open(file_path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None) # Skip header row
            if header:
                for row in reader:
                    if row: # Ensure the row isn't empty
                        processed_ids.add(row[0].strip())
        return processed_ids
    except Exception as e:
        print(f"⚠️ Warning: Could not read tracker history ({e}). Proceeding without deduplication.")
        return processed_ids

# ---------------------------------------------------------------------------
# STAGE 1: Local Job Searching & Scraping (LinkedIn Guest API)
# ---------------------------------------------------------------------------
def search_linkedin_jobs(keywords="Machine Learning", location="Hyderabad"):
    print(f"🔍 Searching for '{keywords}' jobs in '{location}'...")
    url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    params = {"keywords": keywords, "location": location, "f_TPR": "r604800", "start": 0}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            return []
    except Exception:
        return []
        
    soup = BeautifulSoup(response.text, 'html.parser')
    job_cards = soup.find_all('li')
    
    jobs = []
    for card in job_cards:
        title_tag = card.find('h3', class_='base-search-card__title')
        company_tag = card.find('h4', class_='base-search-card__subtitle')
        link_tag = card.find('a', class_='base-card__full-link')
        
        if title_tag and company_tag and link_tag:
            href = link_tag['href']
            job_id = href.split('?')[0].split('-')[-1].strip()
            jobs.append({
                "id": job_id,
                "title": title_tag.text.strip(),
                "company": company_tag.text.strip(),
                "url": href
            })
    print(f"✅ Found {len(jobs)} jobs total via search results.")
    return jobs

def get_job_description(job_url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        response = requests.get(job_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            desc_div = soup.find('div', class_='description__text')
            if desc_div:
                return desc_div.get_text(separator="\n", strip=True)
    except Exception:
        pass
    return "Description text block not found."

# ---------------------------------------------------------------------------
# STAGE 2: Local Tailoring Core via Qwen 2.5 (3B)
# ---------------------------------------------------------------------------
def tailor_profile_and_cover_letter(raw_resume_text, job_description):
    print(f"🦙 Prompting local model ({MODEL_NAME}) to optimize assets...")
    
    prompt = f"""
    You are an expert technical resume writer. Review the candidate's base resume and the job description provided below.
    Rewrite the 'summary', and adjust the phrasing in 'skills' and 'experience' to target the specific requirements of the job. Do not invent fake jobs.
    
    CRITICAL: You must return your response STRICTLY as a valid JSON object. Do not include markdown code blocks (like ```json), do not include intro text, and do not include conversational fluff.
    
    Expected JSON Structure:
    {{
        "summary": "Your rewritten text summary",
        "skills": ["Skill1", "Skill2", "Skill3"],
        "experience": [
            {{
                "role": "Role Title",
                "company": "Company Name",
                "description": "Tailored description focusing on target keywords"
            }}
        ]
    }}

    Candidate Raw Resume:
    {raw_resume_text}

    Target Job Description:
    {job_description}
    """
    
    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False, "format": "json"}
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=90)
        if response.status_code == 200:
            raw_text = response.json().get("response", "").strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("```").replace("json", "", 1).strip()
            return json.loads(raw_text)
    except Exception as e:
        print(f"❌ Local LLM processing error: {e}")
        
    return None

# ---------------------------------------------------------------------------
# STAGE 3: Document Compilation Engine (Resume and Cover Letter PDFs)
# ---------------------------------------------------------------------------
class DocumentPDF(FPDF):
    def __init__(self, doc_title):
        super().__init__()
        self.doc_title = doc_title
        
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, self.doc_title, ln=True, align="C")
        self.ln(5)

def build_pdf_cv(data, filename):
    pdf = DocumentPDF("TAILORED CURRICULUM VITAE")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "Professional Summary", ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, data.get('summary', ''))
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "Technical Skills", ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    skills = data.get('skills', [])
    pdf.multi_cell(0, 5, ", ".join(skills) if isinstance(skills, list) else str(skills))
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "Work Experience", ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)
    
    for item in data.get('experience', []):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, f"{item.get('role', 'Engineer')} - {item.get('company', '')}", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, item.get('description', ''))
        pdf.ln(3)
        
    pdf.output(filename)
    print(f"✅ Generated Resume: {filename}")

def build_pdf_cover_letter(data, filename):
    pdf = DocumentPDF("COVER LETTER")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "", 11)
    letter_text = data.get('cover_letter', 'Cover letter compilation failed.')
    pdf.multi_cell(0, 6, letter_text)
    
    pdf.output(filename)
    print(f"✅ Generated Cover Letter: {filename}")

# ---------------------------------------------------------------------------
# STAGE 4: Spreadsheet Reporting & Workflows
# ---------------------------------------------------------------------------
def log_job_to_tracker(job, cv_file, cl_file, approval, submission, notes=""):
    file_exists = os.path.isfile(CSV_TRACKER_FILE)
    with open(CSV_TRACKER_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Job ID", "Company", "Job Title", "Location", "Job URL", "Date Found", "Tailored CV", "Cover Letter", "Approval Status", "Submission Status", "Notes"])
        writer.writerow([job['id'], job['company'], job['title'], "Hyderabad", job['url'], datetime.now().strftime("%Y-%m-%d"), cv_file, cl_file, approval, submission, notes])

def process_single_job(job, raw_resume_text):
    print("\n" + "="*60)
    print(f"PROCESSING JOB: {job['title']} at {job['company']}")
    print("="*60)
    
    full_description = get_job_description(job['url'])
    if "Description text block not found." in full_description:
        print("⚠️ Description missing. Skipping application.")
        return

    tailored_data = tailor_profile_and_cover_letter(raw_resume_text, full_description)
    if not tailored_data:
        print("❌ AI tailoring failed for this role.")
        return

    clean_company = "".join(x for x in job['company'] if x.isalnum())
    cv_filename = f"Resume_Tailored_{clean_company}_{job['id']}.pdf"
    cl_filename = f"CoverLetter_{clean_company}_{job['id']}.pdf"
    
    build_pdf_cv(tailored_data, cv_filename)
    build_pdf_cover_letter(tailored_data, cl_filename)
    
    print(f"\n👉 Assets Ready For Review: \n📄 {cv_filename}\n✉️ {cl_filename}")
    approval = input("Apply to this role? (yes/no/skip): ").strip().lower()
    
    if approval == 'yes':
        approval_status, submission_status, notes = "Approved", "Submitted", "Applied successfully."
        print("🚀 [SIMULATION] Assets transmitted directly to submission endpoints!")
    elif approval == 'skip':
        approval_status, submission_status, notes = "Skipped", "Not Started", "User bypassed listing."
    else:
        approval_status, submission_status, notes = "Rejected", "Not Started", "User disliked output files."
        
    log_job_to_tracker(job, cv_filename, cl_filename, approval_status, submission_status, notes)

# ---------------------------------------------------------------------------
# MAIN PROCESS EXECUTION
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Step 1: Read your personal base file once at initialization
    raw_resume_content = extract_text_from_pdf(INPUT_RESUME_PDF)
    
    if raw_resume_content:
        # Step 2: Fetch previously processed job IDs from the tracker file
        existing_job_ids = get_already_processed_job_ids()
        if existing_job_ids:
            print(f"ℹ️ Loaded {len(existing_job_ids)} previously processed Job IDs from '{CSV_TRACKER_FILE}'.")
            
        # Step 3: Scrape active listings
        job_results = search_linkedin_jobs(keywords="Machine Learning", location="Hyderabad")
        
        if job_results:
            print(f"\n🚀 Batch starting over {len(job_results)} found listings...")
            for idx, target_job in enumerate(job_results, start=1):
                print(f"\n[Job {idx}/{len(job_results)}]")
                
                # Check if the job ID has already been logged
                if target_job['id'] in existing_job_ids:
                    print(f"⏭️ Skipping Job ID {target_job['id']} ({target_job['title']} at {target_job['company']}) - Already exists in tracker.")
                    continue
                    
                try:
                    process_single_job(target_job, raw_resume_content)
                except Exception as loop_error:
                    print(f"❌ Core processing crash on asset index {idx}: {loop_error}")
            print(f"\n🏁 Finished. Review updates inside your spreadsheet tracker: {CSV_TRACKER_FILE}")
        else:
            print("No jobs found matching your filters.")