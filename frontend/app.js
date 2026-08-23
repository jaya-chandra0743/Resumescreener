// State Management
let state = {
  currentJobId: null,
  jobs: [],
  candidates: [],
  results: [],
  activeFilter: 'all',
  systemStatus: {}
};

// Preset Job Templates
const JOB_TEMPLATES = {
  backend: {
    title: "Senior Java Backend Engineer",
    description: `We are looking for a Senior Java Backend Engineer with 3+ years of experience to design and scale microservices.

Required Skills:
- Java
- Spring Boot
- REST API
- SQL
- Docker
- Git

Good to Have:
- Redis
- AWS
- Kubernetes

Responsibilities:
- Build low-latency backend microservices using Java and Spring Boot.
- Design resilient REST APIs and integrate PostgreSQL databases.
- Containerize services with Docker and manage CI/CD pipelines.`
  },
  fullstack: {
    title: "Full Stack Software Engineer",
    description: `Seeking a Full Stack Software Engineer with 2+ years of experience in Python and modern JavaScript frameworks.

Required Skills:
- Python
- FastAPI
- React
- JavaScript
- SQL
- Git

Good to Have:
- TypeScript
- Tailwind CSS
- Docker

Responsibilities:
- Develop interactive user interfaces using React and Tailwind.
- Build performant REST APIs using Python and FastAPI.
- Manage database models with PostgreSQL and SQLite.`
  },
  data: {
    title: "Data Scientist / Machine Learning Engineer",
    description: `Looking for a Data Scientist with 2+ years of experience in Python, predictive modeling, and NLP.

Required Skills:
- Python
- Machine Learning
- Pandas
- Scikit-Learn
- SQL
- Git

Good to Have:
- PyTorch
- Deep Learning
- AWS
- NLP

Responsibilities:
- Build and train machine learning models for production pipelines.
- Perform exploratory data analysis using Pandas, NumPy, and SQL.
- Deploy machine learning inference services.`
  }
};

// Utility: API caller
async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let errorText = "API request failed";
    try {
      const errJson = await response.json();
      errorText = errJson.detail || errorText;
    } catch {
      errorText = await response.text();
    }
    throw new Error(errorText);
  }
  return response.json();
}

function escapeHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, match => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[match]));
}

// Initialization
async function initApp() {
  await checkHealth();
  await loadJobs();
  await loadCandidates();
}

async function checkHealth() {
  try {
    const health = await api('/api/health');
    state.systemStatus = health;
    const modeText = health.llm_mode === 'hybrid_llm'
      ? `Hybrid AI Mode (${health.model})`
      : 'Deterministic Explainable Mode';
    document.getElementById('systemModeText').innerText = modeText;
  } catch (err) {
    document.getElementById('systemModeText').innerText = 'Offline Mode';
  }
}

// Job Templates
function fillJobTemplate(templateKey) {
  const template = JOB_TEMPLATES[templateKey];
  if (template) {
    document.getElementById('jobTitle').value = template.title;
    document.getElementById('jobDesc').value = template.description;
  }
}

// Job Management
async function handleCreateJob() {
  const title = document.getElementById('jobTitle').value.trim();
  const description = document.getElementById('jobDesc').value.trim();
  const alertBox = document.getElementById('jobAlert');

  if (!title || !description) {
    showAlert(alertBox, 'Please provide both job title and description.', 'error');
    return;
  }

  const btn = document.getElementById('btnCreateJob');
  btn.disabled = true;
  btn.innerText = 'Creating...';

  try {
    const job = await api('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description })
    });

    showAlert(alertBox, `✓ Created "${job.title}" (#${job.id}) with ${job.requirements.skills.length} extracted skills!`, 'success');
    state.currentJobId = job.id;
    await loadJobs();
  } catch (err) {
    showAlert(alertBox, `✕ Error: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.innerText = 'Create Job Posting';
  }
}

async function loadJobs() {
  try {
    const jobs = await api('/api/jobs');
    state.jobs = jobs;
    const select = document.getElementById('jobSelect');

    if (jobs.length === 0) {
      select.innerHTML = '<option value="">No jobs created yet</option>';
      document.getElementById('statJobs').innerText = '0';
      return;
    }

    document.getElementById('statJobs').innerText = jobs.length;
    select.innerHTML = jobs.map(j => `
      <option value="${j.id}" ${state.currentJobId === j.id ? 'selected' : ''}>
        #${j.id} · ${escapeHtml(j.title)} (${j.screened_count} screened)
      </option>
    `).join('');

    if (!state.currentJobId && jobs.length > 0) {
      state.currentJobId = jobs[0].id;
    }
    
    if (state.currentJobId) {
      await loadJobResults(state.currentJobId);
    }
  } catch (err) {
    console.error('Failed to load jobs:', err);
  }
}

function handleJobChange() {
  const select = document.getElementById('jobSelect');
  state.currentJobId = parseInt(select.value, 10);
  if (state.currentJobId) {
    loadJobResults(state.currentJobId);
  }
}

// Candidates Management & Upload
function handleFileSelection(input) {
  const summaryBox = document.getElementById('fileListSummary');
  if (!input.files || input.files.length === 0) {
    summaryBox.classList.add('hidden');
    return;
  }
  const fileNames = Array.from(input.files).map(f => `📄 ${escapeHtml(f.name)} (${(f.size / 1024).toFixed(1)} KB)`).join('<br>');
  summaryBox.innerHTML = `<strong>${input.files.length} file(s) selected:</strong><br>${fileNames}`;
  summaryBox.classList.remove('hidden');
}

async function handleUploadCandidates() {
  const fileInput = document.getElementById('resumeFiles');
  const alertBox = document.getElementById('candidateAlert');

  if (!fileInput.files || fileInput.files.length === 0) {
    showAlert(alertBox, 'Please select one or more resume files (PDF / TXT / MD).', 'error');
    return;
  }

  const btn = document.getElementById('btnUpload');
  btn.disabled = true;
  btn.innerText = 'Parsing Resumes...';

  const resultsSummary = [];
  let successCount = 0;

  for (const file of fileInput.files) {
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await api('/api/candidates', {
        method: 'POST',
        body: formData
      });
      resultsSummary.push(`✓ <strong>${escapeHtml(res.profile.name)}</strong> · ${res.profile.skills.length} skills extracted (${escapeHtml(file.name)})`);
      successCount++;
    } catch (err) {
      resultsSummary.push(`✕ <strong>${escapeHtml(file.name)}</strong>: ${escapeHtml(err.message)}`);
    }
  }

  showAlert(alertBox, resultsSummary.join('<br>'), successCount > 0 ? 'success' : 'error');
  btn.disabled = false;
  btn.innerText = 'Parse & Save Resumes';
  fileInput.value = '';
  document.getElementById('fileListSummary').classList.add('hidden');

  await loadCandidates();
}

async function loadCandidates() {
  try {
    const candidates = await api('/api/candidates');
    state.candidates = candidates;
    document.getElementById('statCandidates').innerText = candidates.length;
  } catch (err) {
    console.error('Failed to load candidates:', err);
  }
}

// Screening & Results
async function handleScreen() {
  if (!state.currentJobId) {
    alert('Please create or select a job posting first.');
    return;
  }

  const btn = document.getElementById('btnScreen');
  btn.disabled = true;
  btn.innerHTML = '<span>Screening...</span>';

  try {
    const results = await api(`/api/screen?job_id=${state.currentJobId}`, { method: 'POST' });
    state.results = results;
    updateCounts();
    renderResults();
  } catch (err) {
    alert(`Screening failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="8"></circle>
        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>
      <span>Screen Candidates</span>
    `;
  }
}

async function loadJobResults(jobId) {
  try {
    const rawResults = await api(`/api/results/${jobId}`);
    state.results = rawResults.map(r => ({
      candidate_id: r.candidate_id,
      name: r.name,
      filename: r.filename,
      email: r.email,
      score: r.score,
      score_1_to_10: r.score_1_to_10,
      status: r.status,
      mode: r.mode,
      justification: r.result?.justification || '',
      skill_gaps: r.result?.skill_gaps || [],
      strengths: r.result?.strengths || [],
      subscores: r.result?.subscores || {}
    }));
    updateCounts();
    renderResults();
  } catch (err) {
    console.error('Failed to load results:', err);
  }
}

function updateCounts() {
  const allCount = state.results.length;
  const shortlistedCount = state.results.filter(r => r.status === 'Shortlisted').length;
  const reviewCount = state.results.filter(r => r.status === 'Under Review').length;
  const rejectedCount = state.results.filter(r => r.status === 'Not Recommended').length;

  document.getElementById('countAll').innerText = allCount;
  document.getElementById('countShortlisted').innerText = shortlistedCount;
  document.getElementById('countReview').innerText = reviewCount;
  document.getElementById('countRejected').innerText = rejectedCount;

  document.getElementById('statShortlisted').innerText = shortlistedCount;

  if (allCount > 0) {
    const topScore = Math.max(...state.results.map(r => r.score));
    document.getElementById('statAvgScore').innerText = `${topScore}%`;
  } else {
    document.getElementById('statAvgScore').innerText = '--';
  }
}

function setFilter(filterType, element) {
  state.activeFilter = filterType;
  document.querySelectorAll('.filter-tab').forEach(el => el.classList.remove('active'));
  if (element) element.classList.add('active');
  renderResults();
}

function renderResults() {
  const container = document.getElementById('resultsContainer');
  let filtered = state.results;

  if (state.activeFilter !== 'all') {
    filtered = filtered.filter(r => r.status === state.activeFilter);
  }

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📂</div>
        <h3>No candidates in this category</h3>
        <p>${state.results.length === 0 ? 'Click "Screen Candidates" to analyze the uploaded resumes.' : 'No candidates match the active filter status.'}</p>
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map((c, index) => {
    const statusClass = c.status === 'Shortlisted' ? 'shortlisted' : (c.status === 'Under Review' ? 'under-review' : 'not-recommended');
    const fillClass = c.score >= 75 ? 'high' : (c.score >= 50 ? 'mid' : 'low');

    return `
      <div class="candidate-card">
        <div class="rank-badge">#${index + 1}</div>
        
        <div class="candidate-info">
          <div class="candidate-name-row">
            <span class="candidate-name">${escapeHtml(c.name)}</span>
            <span class="status-tag ${statusClass}">${escapeHtml(c.status)}</span>
          </div>
          
          <div class="candidate-meta">
            <span>📄 ${escapeHtml(c.filename || 'Resume')}</span>
            ${c.email ? `<span>✉️ ${escapeHtml(c.email)}</span>` : ''}
            <span>⚙️ ${escapeHtml(c.mode)}</span>
          </div>

          <p class="candidate-preview-justification">${escapeHtml(c.justification)}</p>
        </div>

        <div class="score-display">
          <div class="score-pct">${c.score}%</div>
          <div class="score-10">${c.score_1_to_10} / 10 Fit</div>
          <div class="score-progress-bar">
            <div class="score-progress-fill ${fillClass}" style="width: ${c.score}%;"></div>
          </div>
        </div>

        <div class="candidate-actions">
          <button class="btn btn-secondary btn-sm" onclick="inspectEvidence(${state.currentJobId}, ${c.candidate_id})">
            Inspect Evidence
          </button>
        </div>
      </div>
    `;
  }).join('');
}

// Evidence Inspection Modal
async function inspectEvidence(jobId, candidateId) {
  try {
    const data = await api(`/api/results/${jobId}/${candidateId}`);
    const r = data.result;
    const p = data.profile;
    const modalContent = document.getElementById('modalContent');

    const statusClass = data.status === 'Shortlisted' ? 'shortlisted' : (data.status === 'Under Review' ? 'under-review' : 'not-recommended');

    modalContent.innerHTML = `
      <div class="modal-header-banner">
        <div class="brand-eyebrow">EXPLAINABLE CANDIDATE REPORT</div>
        <h2 class="modal-candidate-name">${escapeHtml(data.name)}</h2>
        <div class="candidate-meta" style="margin-top: 4px;">
          <span>📄 ${escapeHtml(data.filename || 'Uploaded Resume')}</span>
          ${data.email ? `<span>✉️ ${escapeHtml(data.email)}</span>` : ''}
          ${data.phone ? `<span>📞 ${escapeHtml(data.phone)}</span>` : ''}
        </div>
        <div class="modal-score-badge">
          <span class="status-tag ${statusClass}">${escapeHtml(data.status)}</span>
          <span>• Overall Score: <strong>${data.score}%</strong> (${data.score_1_to_10} / 10)</span>
          <span>• Engine: <code>${escapeHtml(data.mode)}</code></span>
        </div>
      </div>

      <div class="section-title">Hiring Justification & Reasoning</div>
      <div class="justification-card">
        ${escapeHtml(r.justification || 'No justification provided.')}
      </div>

      ${r.subscores ? `
        <div class="section-title">Evaluation Subscores</div>
        <div class="subscores-grid">
          <div class="subscore-box">
            <div class="subscore-value">${r.subscores.skills ?? '--'}%</div>
            <div class="subscore-label">Required Skills</div>
          </div>
          <div class="subscore-box">
            <div class="subscore-value">${r.subscores.experience ?? '--'}%</div>
            <div class="subscore-label">Experience Fit</div>
          </div>
          <div class="subscore-box">
            <div class="subscore-value">${r.subscores.education ?? '--'}%</div>
            <div class="subscore-label">Education</div>
          </div>
          <div class="subscore-box">
            <div class="subscore-value">${r.subscores.projects ?? '--'}%</div>
            <div class="subscore-label">Projects Relevance</div>
          </div>
        </div>
      ` : ''}

      <div class="section-title">Extracted Skills Evidence Map</div>
      <div class="evidence-list">
        ${(r.evidence || []).map(e => `
          <div class="evidence-row ${e.level.toLowerCase()}">
            <div class="evidence-header">
              <span>${escapeHtml(e.skill)}</span>
              <span>${e.level}</span>
            </div>
            <div>${escapeHtml(e.evidence)}</div>
          </div>
        `).join('')}
      </div>

      <div class="section-title">Skill Gaps & Missing Requirements</div>
      <div class="tags-wrap">
        ${(r.skill_gaps && r.skill_gaps.length > 0)
          ? r.skill_gaps.map(g => `<span class="pill-tag gap">✕ ${escapeHtml(g)}</span>`).join('')
          : '<span style="font-size: 13px; color: #10b981;">✓ No critical skill gaps identified</span>'}
      </div>

      ${r.strengths && r.strengths.length > 0 ? `
        <div class="section-title">Key Candidate Strengths</div>
        <div class="tags-wrap">
          ${r.strengths.map(s => `<span class="pill-tag strength">★ ${escapeHtml(s)}</span>`).join('')}
        </div>
      ` : ''}
    `;

    document.getElementById('evidenceModal').classList.remove('hidden');
  } catch (err) {
    alert(`Failed to load evidence: ${err.message}`);
  }
}

function closeModal() {
  document.getElementById('evidenceModal').classList.add('hidden');
}

function handleModalBackdropClick(event) {
  if (event.target === document.getElementById('evidenceModal')) {
    closeModal();
  }
}

// Export Report
function exportReport(format) {
  if (!state.currentJobId) {
    alert('Please select a job role first.');
    return;
  }
  window.open(`/api/export/${state.currentJobId}?format=${format}`, '_blank');
}

// Helpers
function showAlert(el, message, type) {
  el.className = `alert-box ${type}`;
  el.innerHTML = message;
  el.classList.remove('hidden');
}

// Initialize on DOM load
window.addEventListener('DOMContentLoaded', initApp);
