/* Bid Studio app runtime. Each /app/* page sets window.WS_ID and window.PAGE_NEEDS
   (the datasets that page renders); only those are fetched. */
let currentWsId = window.WS_ID;
const PAGE_NEEDS = new Set(window.PAGE_NEEDS || []);
const need = (k) => PAGE_NEEDS.has(k);
const SINK = {}; // absorbs writes for elements that are not on this page
const E = (id) => document.getElementById(id) || SINK;

async function loadWorkspaces() {
  const list = await api("/api/v1/workspaces");
  const sel = document.getElementById("wsSelect");
  if (!sel) return;
  sel.innerHTML = list.map(w => `<option value="${w.id}" ${w.id === currentWsId ? "selected" : ""}>${w.brand_name} (${w.slug})</option>`).join("");
}

function goToWorkspace(id) {
  const url = new URL(window.location.href);
  url.searchParams.set("workspace_id", String(id));
  window.location.href = url.toString();
}

function switchWorkspace() {
  goToWorkspace(Number(document.getElementById("wsSelect").value));
}

let noticeOffset = 0;
    const noticeLimit = 6;
    let totalNotices = 0;

    async function api(path, method = "GET", body = null) {
      const opts = { method, headers: { "Content-Type": "application/json" } };
      if (body) opts.body = JSON.stringify(body);
      const res = await fetch(path, opts);
      if (!res.ok) {
        const txt = await res.text();
        alert(`Error ${res.status}: ${txt}`);
        throw new Error(txt);
      }
      return res.json();
    }

    async function apiNotices(path) {
      const res = await fetch(path);
      if (!res.ok) {
        const txt = await res.text();
        alert(`Error ${res.status}: ${txt}`);
        throw new Error(txt);
      }
      const totalHeader = res.headers.get("X-Total-Count");
      const items = await res.json();
      return { items, total: totalHeader ? Number(totalHeader) : items.length };
    }

    function prevNoticePage() {
      noticeOffset = Math.max(0, noticeOffset - noticeLimit);
      refreshAll();
    }

    function nextNoticePage() {
      if (noticeOffset + noticeLimit < totalNotices) {
        noticeOffset += noticeLimit;
        refreshAll();
      }
    }

    async function refreshAll() {
      const q = E("feedSearch")?.value || "";
      const nType = E("feedType")?.value || "";
      const noticeParams = new URLSearchParams({
        workspace_id: String(currentWsId),
        limit: String(noticeLimit),
        offset: String(noticeOffset)
      });
      if (q) noticeParams.set("q", q);
      if (nType) noticeParams.set("notice_type", nType);

      const [summary, noticePage, grants, answers, evidence, orders, queue, deliveries, proposals, techdocs, compliance, assets, reviewers, reviews, debriefs, clarifs, pricingTemplates, matrices, svs, alertSubs, intelReports, frameworks, cohorts, enrolments, buyerDrafts, members, businessDocs, legalMatters] = await Promise.all([
        need("summary") ? api(`/api/v1/workspaces/${currentWsId}/summary`) : Promise.resolve({ total_order_revenue: 0 }),
        need("notices") ? apiNotices(`/api/v1/notices?${noticeParams.toString()}`) : Promise.resolve({ items: [], total: 0 }),
        need("grants") ? api(`/api/v1/grants/calls?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("answers") ? api(`/api/v1/answer-library?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("evidence") ? api(`/api/v1/evidence-library?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("orders") ? api(`/api/v1/orders?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("queue") ? api(`/api/v1/quality-queue?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("deliveries") ? api(`/api/v1/deliveries?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("proposals") ? api(`/api/v1/grants/proposals?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("techdocs") ? api(`/api/v1/tech-docs?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("compliance") ? api(`/api/v1/compliance/packs?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("assets") ? api(`/api/v1/bidder-assets?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("reviewers") ? api("/api/v1/marketplace/reviewers") : Promise.resolve([]),
        need("reviews") ? api(`/api/v1/marketplace/reviews?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("debriefs") ? api(`/api/v1/debriefs/outcomes?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("clarifs") ? api(`/api/v1/clarifications?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("pricingTemplates") ? api("/api/v1/pricing/templates") : Promise.resolve([]),
        need("matrices") ? api(`/api/v1/pricing/matrices?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("svs") ? api(`/api/v1/social-value?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("alertSubs") ? api(`/api/v1/alerts/subscriptions?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("intelReports") ? api(`/api/v1/intelligence/reports?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("frameworks") ? api(`/api/v1/frameworks?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("cohorts") ? api("/api/v1/training/cohorts") : Promise.resolve([]),
        need("enrolments") ? api(`/api/v1/training/enrolments?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("buyerDrafts") ? api(`/api/v1/public-sector/drafts?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("members") ? api(`/api/v1/workspaces/${currentWsId}/members`) : Promise.resolve([]),
        need("businessDocs") ? api(`/api/v1/business-docs?workspace_id=${currentWsId}`) : Promise.resolve([]),
        need("legalMatters") ? api(`/api/v1/legal-contracts?workspace_id=${currentWsId}`) : Promise.resolve({ items: [] })
      ]);

      const pmSel = E("pmTemplate");
      const prevTmpl = pmSel.value;
      pmSel.innerHTML = `<option value="">Custom Lines (Riverbend Default)</option>` + pricingTemplates.map(t => `<option value="${t.id}">${t.name} (${t.default_margin_pct}% margin)</option>`).join("");
      if (prevTmpl) pmSel.value = prevTmpl;

      const notices = noticePage.items;
      totalNotices = noticePage.total;
      const totalPages = Math.max(1, Math.ceil(totalNotices / noticeLimit));
      const currentPage = Math.floor(noticeOffset / noticeLimit) + 1;

      E("statNotices").textContent = totalNotices;
      E("statGrants").textContent = grants.length;
      E("statAnswers").textContent = `${answers.length} / ${evidence.length}`;
      E("statQueue").textContent = summary.pending_qa_count;
      E("statWinRate").textContent = `${summary.win_rate_pct}%`;
      E("statRevenue").textContent = `£${summary.total_order_revenue.toLocaleString()}`;
      E("noticePageLabel").textContent = `Page ${currentPage} of ${totalPages} (${totalNotices} total)`;
      E("btnPrevNotices").disabled = noticeOffset <= 0;
      E("btnNextNotices").disabled = noticeOffset + noticeLimit >= totalNotices;

      E("feedList").innerHTML = notices.map(n => `<div class="row-item">
        <span class="badge">${n.notice_type}</span> <strong>#${n.id} ${n.title}</strong> — ${n.funder_or_buyer} (${n.currency} ${n.contract_value.toLocaleString()})
        <div class="muted">${n.ai_summary}</div>
      </div>`).join("") || `<div class="muted">No matching notices on this page.</div>`;

      E("answerLibraryList").innerHTML = answers.slice(0, 5).map(a => `<div class="row-item">
        <span class="badge">${a.category}</span> <strong>${a.question_pattern}</strong>
        <div class="muted">${a.answer_text}</div>
      </div>`).join("") || `<div class="muted">No answer library items in this workspace.</div>`;

      E("evidenceLibraryList").innerHTML = evidence.slice(0, 5).map(e => `<div class="row-item">
        <span class="badge">${e.evidence_type}</span> <strong>${e.title}</strong> (${e.buyer_format})
        <div class="muted">${e.summary}</div>
      </div>`).join("") || `<div class="muted">No evidence items in this workspace.</div>`;

      E("ordersList").innerHTML = orders.slice(0, 5).map(o => `<div class="row-item">
        <span class="badge">${o.source}</span> <strong>#${o.id} ${o.service_type}</strong> — ${o.customer_email} (${o.currency} ${o.amount.toLocaleString()})
      </div>`).join("") || `<div class="muted">No orders recorded yet.</div>`;

      E("queueList").innerHTML = queue.map(qItem => `<div class="row-item">
        <strong>#${qItem.id} ${qItem.title}</strong> (${qItem.item_type}) — <span class="badge">${qItem.status}</span> Score: ${qItem.review_score ?? "-"}
        <div class="inline-actions">
          <button class="small" onclick="reviewQueueItem(${qItem.id}, 'approved')">Approve QA</button>
          <button class="small secondary" onclick="reviewQueueItem(${qItem.id}, 'changes_requested')">Request Changes</button>
        </div>
      </div>`).join("") || `<div class="muted">Quality queue is empty.</div>`;

      E("deliveriesList").innerHTML = deliveries.slice(0, 5).map(d => `<div class="row-item">
        <span class="badge">${d.delivery_type}</span> To: <strong>${d.recipient_email}</strong> — ${d.subject}
      </div>`).join("") || `<div class="muted">No deliveries sent yet.</div>`;

      E("grantCallsList").innerHTML = grants.map(g => `<div class="row-item">
        <span class="badge">${g.source_portal}</span> <strong>#${g.id} ${g.title}</strong> (${g.currency} ${g.contract_value.toLocaleString()})
        <div class="inline-actions">
          <button class="small" onclick="extractGrantCriteria(${g.id})">Extract Criteria (${g.structured_criteria.length})</button>
          <button class="small secondary" onclick="draftProposalForCall(${g.id}, ${g.contract_value})">Draft Proposal</button>
        </div>
      </div>`).join("");

      window.__grantProposals = proposals;
      E("grantProposalsList").innerHTML = proposals.map(p => `<div class="row-item">
        <strong>${p.title}</strong> — ${p.funder_type} | Weighted Score: <strong>${p.total_weighted_score}%</strong> | Status: <span class="badge">${p.status}</span>
        <div class="inline-actions">
          <button class="small" onclick="submitGrantReview(${p.id})">Submit to Quality Queue</button>
          <button class="small secondary" onclick="toggleEditProposal(${p.id})">Edit Sections</button>
          <button class="small secondary" onclick="exportGrantProposal(${p.id})">Export Markdown</button>
        </div>
        <div id="gpEdit-${p.id}" style="display:none; margin-top:8px;">
          ${(p.sections || []).map((s, idx) => `<div style="margin-bottom:8px;">
            <div class="muted"><strong>${s.criterion_id} — ${s.title}</strong> (Weight ${s.weight}%, Max ${s.max_score})</div>
            <textarea id="gpSecText-${p.id}-${idx}" rows="2">${s.draft_text || ""}</textarea>
            <input id="gpSecScore-${p.id}-${idx}" type="number" step="0.5" value="${s.self_score}" style="width:120px; margin-top:4px;" />
          </div>`).join("")}
          <button class="small" onclick="saveProposalSections(${p.id})">Save Sections &amp; Recalculate Score</button>
        </div>
      </div>`).join("");

      E("techDocsList").innerHTML = techdocs.map(d => `<div class="row-item">
        <strong>${d.title}</strong> (${d.doc_type}, ${d.currency} ${d.fixed_fee}) — Stage: <span class="badge">${d.pipeline_stage}</span>
        <div class="inline-actions">
          <button class="small secondary" onclick="submitTechDocQA(${d.id})">1. Submit to QA</button>
          <button class="small secondary" onclick="approveTechDocQA(${d.id})">2. Approve QA</button>
          <button class="small" onclick="deliverTechDoc(${d.id})">3. Deliver Email</button>
          <button class="small secondary" onclick="exportTechDoc(${d.id})">Export Markdown</button>
        </div>
      </div>`).join("");

      E("complianceList").innerHTML = compliance.map(c => `<div class="row-item">
        <strong>${c.title}</strong> (${c.pack_type}) — Status: <span class="badge">${c.status}</span> (${c.questionnaire_items.filter(q => q.status === 'matched').length}/${c.questionnaire_items.length} auto-matched)
        <div class="inline-actions"><button class="small secondary" onclick="exportCompliancePack(${c.id})">Export Markdown</button></div>
        ${c.questionnaire_items.map(q => `<div class="muted" style="margin-top:4px;">&bull; <strong>${q.id}</strong>: ${q.question} &rarr; <span class="badge">${q.status} (${Math.round((q.confidence || 0)*100)}%)</span> ${q.matched_answer_text || ""}</div>`).join("")}
      </div>`).join("");

      E("assetsList").innerHTML = assets.map(a => `<div class="row-item">
        <strong>${a.title}</strong> (${a.asset_type}) — <span class="badge">${a.status}</span> (Evidence ID: ${a.promoted_evidence_id || "-"})
        <div class="inline-actions">
          ${a.status !== 'promoted' ? `<button class="small" onclick="promoteBidderAsset(${a.id})">Promote to Evidence</button>` : ""}
          <button class="small secondary" onclick="exportBidderAsset(${a.id})">Export Markdown</button>
        </div>
      </div>`).join("");

      E("reviewersList").innerHTML = reviewers.map(r => `<div class="row-item">
        <strong>${r.full_name}</strong> (${r.specialisms.join(", ")}) — ${r.currency} ${r.flat_fee} ★ ${r.rating}
      </div>`).join("");

      E("reviewsList").innerHTML = reviews.map(rv => `<div class="row-item">
        Review: <strong>${rv.target_title}</strong> — <span class="badge">${rv.status}</span> Score: ${rv.overall_score ?? "Pending"}
        <div class="inline-actions">
          ${rv.status !== 'completed' ? `<button class="small" onclick="scoreMarketplaceReview(${rv.id})">Submit Reviewer Score (84%)</button>` : ""}
          <button class="small secondary" onclick="exportMarketplaceReview(${rv.id})">Export Markdown</button>
        </div>
        ${rv.status === 'completed' ? `<div class="muted">${rv.feedback_summary}</div>` : ""}
      </div>`).join("");

      E("debriefsList").innerHTML = debriefs.map(d => `<div class="row-item">
        <strong>${d.bid_title}</strong> (${d.buyer_name}) — <span class="badge">${d.outcome}</span> | Internal ${d.internal_score} vs Buyer ${d.buyer_score} | Fixes: ${d.next_bid_fixes.length}
        <div class="inline-actions"><button class="small secondary" onclick="exportDebrief(${d.id})">Export Markdown</button></div>
      </div>`).join("");

      E("clarificationsList").innerHTML = clarifs.map(c => `<div class="row-item">
        <strong>${c.tender_title}</strong> (Deadline: ${c.clarification_deadline}) — ${c.questions.length} clarification question(s)
        <div class="inline-actions"><button class="small secondary" onclick="exportClarificationPack(${c.id})">Export Markdown</button></div>
        ${c.questions.map(q => `<div class="muted" style="margin-top:4px;">
          <span class="badge">${q.priority}</span> <span class="badge">${q.status}</span> <strong>${q.id}</strong>: ${q.drafted_question}
          ${q.status !== 'answered' ? `<button class="small secondary" onclick="markClarificationAnswered(${c.id}, '${q.id}')">Mark Answered</button>` : `<div><em>Buyer response:</em> ${q.buyer_response}</div>`}
        </div>`).join("")}
      </div>`).join("");

      E("pricingList").innerHTML = matrices.map(m => `<div class="row-item">
        <strong>${m.bid_title}</strong> — Subtotal ${m.currency} ${m.subtotal.toLocaleString()} &rarr; Total <strong>${m.currency} ${m.total_price.toLocaleString()}</strong>
        <div class="muted">${m.cost_narrative}</div>
        <div class="inline-actions"><button class="small secondary" onclick="exportPriceMatrix(${m.id})">Export Markdown</button></div>
      </div>`).join("");

      E("socialValueList").innerHTML = svs.map(s => `<div class="row-item">
        <strong>${s.bid_title}</strong> (Net Zero ${s.net_zero_target_year})
        <div class="muted">${s.generated_statement}</div>
        <div class="inline-actions"><button class="small secondary" onclick="exportSocialValue(${s.id})">Export Markdown</button></div>
      </div>`).join("");

      E("alertSubsList").innerHTML = alertSubs.map(sub => `<div class="row-item">
        <strong>${sub.subscriber_email}</strong> (${sub.cadence}) — Sectors: ${(sub.sectors || []).join(", ") || "All"}
      </div>`).join("") || `<div class="muted">No subscriptions yet.</div>`;

      E("intelReportsList").innerHTML = intelReports.map(rep => `<div class="row-item">
        <strong>${rep.buyer_name}</strong> — ${rep.awards_analyzed} awards, Total ${rep.total_spend.toLocaleString()}
        <div class="inline-actions"><button class="small secondary" onclick="exportIntelReport(${rep.id})">Export Markdown</button></div>
      </div>`).join("") || `<div class="muted">No intelligence reports saved yet.</div>`;

      E("frameworksList").innerHTML = frameworks.map(f => `<div class="row-item">
        <strong>${f.vehicle_name}</strong> (${f.vehicle_type}) — ${f.completion_pct}% complete (<span class="badge">${f.readiness_status}</span>)
        <div class="inline-actions"><button class="small secondary" onclick="exportFramework(${f.id})">Export Markdown</button></div>
        ${f.checklist.map(ch => `<div class="muted">
          <label><input type="checkbox" ${ch.completed ? "checked" : ""} onchange="toggleFrameworkItem(${f.id}, '${ch.item_id}', this.checked)" /> ${ch.item_id}: ${ch.title}</label>
        </div>`).join("")}
      </div>`).join("");

      E("cohortsList").innerHTML = cohorts.map(c => `<div>
        <strong>${c.title}</strong> — Pack: <em>${c.pack_name}</em> (${c.enrolled_count}/${c.max_seats} enrolled, ${c.currency} ${c.price})
      </div>`).join("");

      E("enrolmentsList").innerHTML = enrolments.map(e => {
        const cohort = cohorts.find(c => c.id === e.cohort_id);
        const nextMod = cohort ? cohort.modules.find(m => !(e.completed_modules || []).includes(m)) : null;
        return `<div class="row-item">
          ${e.learner_name} (${e.learner_email}) — Order #${e.order_id} | Progress: <strong>${e.progress_pct}%</strong>
          ${nextMod ? `<div class="inline-actions"><button class="small secondary" onclick="completeNextModule(${e.id}, ${JSON.stringify(nextMod).replace(/"/g, '&quot;')})">Complete: ${nextMod}</button></div>` : `<span class="badge">Completed</span>`}
        </div>`;
      }).join("");

      E("buyerDraftsList").innerHTML = buyerDrafts.map(b => `<div class="row-item">
        <strong>${b.title}</strong> (${b.authority_name}) — Clarity: <strong>${b.clarity_score}%</strong> | Status: <span class="badge">${b.status}</span>
        ${b.validation_issues.length ? `<div class="muted">Issues: ${b.validation_issues.join(" | ")}</div>` : `<div class="muted">All criteria weights sum to 100% and specification passed clarity checks.</div>`}
        <div class="inline-actions">
          <button class="small" onclick="revalidateBuyerDraft(${b.id})">Re-Validate</button>
          <button class="small secondary" onclick="exportBuyerDraft(${b.id})">Export Tender Pack Markdown</button>
        </div>
      </div>`).join("");

      E("membersList").innerHTML = members.map(m => `<div class="row-item">
        <strong>${m.full_name}</strong> (${m.email}) — <span class="badge">${m.role}</span> | Status: ${m.status}
      </div>`).join("") || `<div class="muted">No members added to this workspace yet.</div>`;

      E("businessDocsList").innerHTML = businessDocs.map(d => `<div class="row-item">
        <strong>${esc(d.title)}</strong> (${esc(d.doc_type.replace(/_/g, " "))}, ${esc(d.currency)} ${d.fixed_fee}) — Stage: <span class="badge">${esc(d.pipeline_stage)}</span>
        <div class="inline-actions">
          <button class="small secondary" onclick="submitBusinessDocQA(${d.id})">1. Submit to QA</button>
          <button class="small secondary" onclick="approveBusinessDocQA(${d.id})">2. Approve QA</button>
          <button class="small" onclick="deliverBusinessDoc(${d.id})">3. Deliver Email</button>
          <button class="small secondary" onclick="exportBusinessDoc(${d.id})">Export Markdown</button>
        </div>
      </div>`).join("") || `<div class="muted">No business documents yet.</div>`;

      E("legalList").innerHTML = legalMatters.items.map(m => {
        const signed = m.status === "lawyer_signed_off" || m.status === "delivered";
        return `<div class="row-item">
        <strong>${esc(m.title)}</strong> (${esc(m.contract_type.replace(/_/g, " "))}, ${esc(m.jurisdiction)}) — <span class="badge">${esc(m.status)}</span>
        <div class="muted">Lawyer: ${m.assigned_lawyer_name ? esc(m.assigned_lawyer_name) + " (" + esc(m.assigned_lawyer_ref) + ")" : "not yet assigned"}${m.signed_off_at ? " | Signed off " + esc(m.signed_off_at) : ""}</div>
        <div class="muted">Instructions: ${esc(m.instructions) || "-"}</div>
        <div class="inline-actions">
          ${!m.assigned_lawyer_name ? `<button class="small" onclick="assignLawyer(${m.id})">Assign lawyer</button>` : ""}
          ${m.assigned_lawyer_name && m.status !== "delivered" ? `<button class="small secondary" onclick="toggleLegalDraft(${m.id})">Lawyer's draft</button><button class="small secondary" onclick="signOffLegal(${m.id})">Lawyer sign-off</button>` : ""}
          ${m.status === "lawyer_signed_off" ? `<button class="small" onclick="deliverLegal(${m.id})">Deliver signed contract</button>` : ""}
          ${signed ? `<button class="small secondary" onclick="exportLegal(${m.id})">Export Markdown</button>` : ""}
        </div>
        <div id="lgDraft-${m.id}" style="display:none; margin-top:8px;">
          <textarea id="lgText-${m.id}" rows="8">${esc(m.draft_content)}</textarea>
          <button class="small" onclick="saveLegalDraft(${m.id})">Save lawyer's draft (voids any earlier sign-off)</button>
        </div>
      </div>`;
      }).join("") || `<div class="muted">No legal matters yet.</div>`;
    }

    async function addAnswerItem() {
      await api("/api/v1/answer-library", "POST", {
        workspace_id: currentWsId,
        question_pattern: E("alTitle").value,
        category: E("alCategory").value,
        answer_text: E("alContent").value,
        tags: [E("alCategory").value]
      });
      refreshAll();
    }

    async function createFeedNotice() {
      await api("/api/v1/notices", "POST", {
        workspace_id: currentWsId,
        notice_type: E("newNoticeType").value,
        title: E("newNoticeTitle").value,
        funder_or_buyer: E("newNoticeBuyer").value,
        sector: E("newNoticeSector").value,
        contract_value: Number(E("newNoticeValue").value || 0)
      });
      noticeOffset = 0;
      refreshAll();
    }

    function renderMarkdownExport(anchorId, previewId, filename, markdown) {
      let wrap = document.getElementById(previewId); // real lookup: E() never returns null
      if (!wrap) {
        wrap = document.createElement("div");
        wrap.id = previewId;
        wrap.style.marginTop = "10px";
        document.getElementById(anchorId).after(wrap);
      }
      wrap.innerHTML = `<div class="inline-actions" style="margin-bottom:6px;">
        <button class="small secondary" id="${previewId}-copy">Copy Markdown</button>
        <button class="small secondary" id="${previewId}-dl">Download ${filename}</button>
      </div><pre></pre>`;
      wrap.querySelector("pre").textContent = markdown;
      wrap.querySelector(`#${previewId}-copy`).onclick = async () => {
        if (navigator.clipboard) await navigator.clipboard.writeText(markdown);
      };
      wrap.querySelector(`#${previewId}-dl`).onclick = () => {
        const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
      };
    }

    async function exportSocialValue(statementId) {
      const data = await api(`/api/v1/social-value/${statementId}/export`);
      renderMarkdownExport("socialValueList", "svExportPreview", `social-value-${statementId}.md`, data.markdown);
    }

    async function exportBuyerDraft(draftId) {
      const data = await api(`/api/v1/public-sector/drafts/${draftId}/export-pack`);
      renderMarkdownExport("buyerDraftsList", "psExportPreview", `tender-pack-${draftId}.md`, data.markdown);
    }

    async function revalidateBuyerDraft(draftId) {
      await api(`/api/v1/public-sector/drafts/${draftId}/validate`, "POST");
      refreshAll();
    }

    async function exportTechDoc(docId) {
      const data = await api(`/api/v1/tech-docs/${docId}/export`);
      renderMarkdownExport("techDocsList", "tdExportPreview", `tech-doc-${docId}.md`, data.markdown);
    }

    async function exportDebrief(outcomeId) {
      const data = await api(`/api/v1/debriefs/outcomes/${outcomeId}/export`);
      renderMarkdownExport("debriefsList", "dbExportPreview", `debrief-${outcomeId}.md`, data.markdown);
    }

    async function exportCompliancePack(packId) {
      const data = await api(`/api/v1/compliance/packs/${packId}/export`);
      renderMarkdownExport("complianceList", "cpExportPreview", `compliance-pack-${packId}.md`, data.markdown);
    }

    async function exportClarificationPack(packId) {
      const data = await api(`/api/v1/clarifications/${packId}/export`);
      renderMarkdownExport("clarificationsList", "cqExportPreview", `clarifications-${packId}.md`, data.markdown);
    }

    async function exportPriceMatrix(matrixId) {
      const data = await api(`/api/v1/pricing/matrices/${matrixId}/export`);
      renderMarkdownExport("pricingList", "pmExportPreview", `pricing-matrix-${matrixId}.md`, data.markdown);
    }

    async function addEvidenceItem() {
      await api("/api/v1/evidence-library", "POST", {
        workspace_id: currentWsId,
        evidence_type: E("evType").value,
        title: E("evTitle").value,
        buyer_format: E("evFormat").value,
        summary: E("evSummary").value
      });
      refreshAll();
    }

    async function exportBidderAsset(assetId) {
      const data = await api(`/api/v1/bidder-assets/${assetId}/export`);
      renderMarkdownExport("assetsList", "baExportPreview", `bidder-asset-${assetId}.md`, data.markdown);
    }

    async function exportMarketplaceReview(reviewId) {
      const data = await api(`/api/v1/marketplace/reviews/${reviewId}/export`);
      renderMarkdownExport("reviewsList", "mrExportPreview", `marketplace-review-${reviewId}.md`, data.markdown);
    }

    async function exportIntelReport(reportId) {
      const data = await api(`/api/v1/intelligence/reports/${reportId}/export`);
      renderMarkdownExport("intelReportsList", "inExportPreview", `intelligence-report-${reportId}.md`, data.markdown);
    }

    async function exportFramework(onboardingId) {
      const data = await api(`/api/v1/frameworks/${onboardingId}/export`);
      renderMarkdownExport("frameworksList", "fwExportPreview", `framework-checklist-${onboardingId}.md`, data.markdown);
    }

    async function createWhiteLabelWorkspace() {
      const ws = await api("/api/v1/workspaces", "POST", {
        slug: E("newWsSlug").value,
        name: E("newWsName").value,
        is_white_label: true,
        brand_name: E("newWsBrand").value || E("newWsName").value
      });
      goToWorkspace(ws.id);
    }

    async function addWorkspaceMember() {
      const member = await api(`/api/v1/workspaces/${currentWsId}/members`, "POST", {
        email: E("memEmail").value,
        full_name: E("memName").value,
        role: E("memRole").value
      });
      E("accessReviewOutput").textContent = JSON.stringify(member, null, 2);
      refreshAll();
    }

    async function draftProposalForCall(noticeId, amount) {
      E("gpNoticeId").value = String(noticeId);
      if (amount) E("gpAmount").value = String(amount);
      await createGrantProposal();
    }

    async function promoteBidderAsset(assetId) {
      await api(`/api/v1/bidder-assets/${assetId}/promote-to-evidence`, "POST");
      refreshAll();
    }

    async function reviewQueueItem(itemId, status) {
      await api(`/api/v1/quality-queue/${itemId}/review`, "POST", {
        assigned_reviewer: "QA Lead",
        status,
        review_score: status === "approved" ? 88 : 62,
        review_notes: status === "approved" ? "Approved by QA Lead." : "Add quantified evidence."
      });
      refreshAll();
    }

    async function extractGrantCriteria(noticeId) {
      await api(`/api/v1/grants/calls/${noticeId}/extract-criteria`, "POST");
      refreshAll();
    }

    async function submitGrantReview(proposalId) {
      await api(`/api/v1/grants/proposals/${proposalId}/submit-review`, "POST");
      refreshAll();
    }

    async function exportGrantProposal(proposalId) {
      const data = await api(`/api/v1/grants/proposals/${proposalId}/export`);
      renderMarkdownExport("grantProposalsList", "grantExportPreview", `grant-proposal-${proposalId}.md`, data.markdown);
    }

    function toggleEditProposal(proposalId) {
      const el = E(`gpEdit-${proposalId}`);
      if (el) el.style.display = el.style.display === "none" ? "block" : "none";
    }

    async function saveProposalSections(proposalId) {
      const prop = (window.__grantProposals || []).find(p => p.id === proposalId);
      if (!prop) return;
      const updated = (prop.sections || []).map((s, idx) => ({
        ...s,
        draft_text: E(`gpSecText-${proposalId}-${idx}`).value,
        self_score: Number(E(`gpSecScore-${proposalId}-${idx}`).value)
      }));
      await api(`/api/v1/grants/proposals/${proposalId}/sections`, "PUT", { sections: updated });
      refreshAll();
    }

    async function createGrantProposal() {
      await api("/api/v1/grants/proposals", "POST", {
        workspace_id: currentWsId,
        notice_id: Number(E("gpNoticeId").value),
        applicant_org: E("gpOrg").value,
        requested_amount: Number(E("gpAmount").value)
      });
      refreshAll();
    }

    async function createTechDoc() {
      await api("/api/v1/tech-docs", "POST", {
        workspace_id: currentWsId,
        doc_type: E("tdType").value,
        title: E("tdTitle").value,
        client_email: E("tdEmail").value,
        fixed_fee: Number(E("tdFee").value)
      });
      refreshAll();
    }

    async function submitTechDocQA(docId) {
      await api(`/api/v1/tech-docs/${docId}/submit-quality`, "POST");
      refreshAll();
    }

    async function approveTechDocQA(docId) {
      await api(`/api/v1/tech-docs/${docId}/review`, "POST", {
        approved: true,
        reviewer_notes: "Technical accuracy and formatting verified."
      });
      refreshAll();
    }

    async function deliverTechDoc(docId) {
      await api(`/api/v1/tech-docs/${docId}/deliver`, "POST");
      refreshAll();
    }

    async function createAndMatchCompliance() {
      const qs = E("cpQuestions").value.split("\n").map(s => s.trim()).filter(Boolean);
      const pack = await api("/api/v1/compliance/packs", "POST", {
        workspace_id: currentWsId,
        pack_type: E("cpType").value,
        title: E("cpTitle").value,
        questions: qs
      });
      await api(`/api/v1/compliance/packs/${pack.id}/auto-match`, "POST");
      refreshAll();
    }

    async function createAndPromoteAsset() {
      const asset = await api("/api/v1/bidder-assets", "POST", {
        workspace_id: currentWsId,
        asset_type: E("baType").value,
        title: E("baTitle").value,
        subject_name: E("baSubject").value,
        content: E("baContent").value
      });
      await api(`/api/v1/bidder-assets/${asset.id}/promote-to-evidence`, "POST");
      refreshAll();
    }

    async function requestMarketplaceReview() {
      const reviewers = await api("/api/v1/marketplace/reviewers");
      if (!reviewers.length) return;
      await api("/api/v1/marketplace/reviews", "POST", {
        workspace_id: currentWsId,
        reviewer_id: reviewers[0].id,
        target_title: E("mrTitle").value,
        buyer_criteria: [
          { name: "Technical Delivery", weight: 60 },
          { name: "Social Value", weight: 40 }
        ],
        draft_excerpt: E("mrExcerpt").value
      });
      refreshAll();
    }

    async function scoreMarketplaceReview(reviewId) {
      await api(`/api/v1/marketplace/reviews/${reviewId}/score`, "POST", {
        criterion_scores: [
          { name: "Technical Delivery", weight: 60, score: 86, max_score: 100 },
          { name: "Social Value", weight: 40, score: 81, max_score: 100 }
        ],
        feedback_summary: "Strong SLA evidence; add named depot commissioning milestones."
      });
      refreshAll();
    }

    async function runDebriefCompare() {
      await api("/api/v1/debriefs/compare", "POST", {
        workspace_id: currentWsId,
        bid_title: E("dbTitle").value,
        buyer_name: E("dbBuyer").value,
        outcome: E("dbOutcome").value,
        criterion_comparisons: [
          { criterion: "Technical Quality", internal_score: 86, buyer_score: 68 },
          { criterion: "Social Value", internal_score: 82, buyer_score: 79 }
        ]
      });
      refreshAll();
    }

    async function analyzeClarifications() {
      await api("/api/v1/clarifications/analyze-pack", "POST", {
        workspace_id: currentWsId,
        tender_title: E("cqTitle").value,
        source_text: E("cqText").value
      });
      refreshAll();
    }

    async function markClarificationAnswered(packId, questionId) {
      await api(`/api/v1/clarifications/${packId}/questions`, "PATCH", {
        question_id: questionId,
        status: "answered",
        buyer_response: "Authority confirmed exact SLA and boundary in Clarification Bulletin #1."
      });
      refreshAll();
    }

    async function createPriceMatrix() {
      const tmplId = E("pmTemplate").value;
      const payload = {
        workspace_id: currentWsId,
        bid_title: E("pmTitle").value,
        margin_pct: Number(E("pmMargin").value)
      };
      if (tmplId) {
        payload.template_id = Number(tmplId);
      } else {
        payload.lines = [
          { category: "Mobilisation", description: "Depot Telemetry Setup", unit: "day", quantity: 10, unit_rate: 800 },
          { category: "Delivery", description: "Route Optimisation Engineering", unit: "day", quantity: 20, unit_rate: 950 }
        ];
      }
      await api("/api/v1/pricing/matrices", "POST", payload);
      refreshAll();
    }

    async function createSocialValue() {
      await api("/api/v1/social-value", "POST", {
        workspace_id: currentWsId,
        bid_title: E("svTitle").value,
        net_zero_target_year: Number(E("svYear").value)
      });
      refreshAll();
    }

    async function subscribeAndGenerateDigest() {
      const sub = await api("/api/v1/alerts/subscriptions", "POST", {
        workspace_id: currentWsId,
        subscriber_email: E("alEmail").value,
        sectors: [E("alSector").value]
      });
      const digest = await api(`/api/v1/alerts/subscriptions/${sub.id}/generate-digest`, "POST");
      E("digestOutput").textContent = JSON.stringify(digest, null, 2);
      refreshAll();
    }

    async function generateBuyerIntel() {
      const report = await api("/api/v1/intelligence/buyer-report", "POST", {
        workspace_id: currentWsId,
        buyer_name: E("inBuyer").value
      });
      E("intelOutput").textContent = JSON.stringify(report, null, 2);
      refreshAll();
    }

    async function createFrameworkOnboarding() {
      await api("/api/v1/frameworks", "POST", {
        workspace_id: currentWsId,
        vehicle_type: E("fwType").value,
        vehicle_name: E("fwName").value,
        authority_name: E("fwAuth").value
      });
      refreshAll();
    }

    async function toggleFrameworkItem(onboardingId, itemId, completed) {
      await api(`/api/v1/frameworks/${onboardingId}/checklist`, "PATCH", {
        item_id: itemId,
        completed,
        notes: completed ? "Verified in Bid Studio" : ""
      });
      refreshAll();
    }

    async function enrolCohort() {
      const cohorts = await api("/api/v1/training/cohorts");
      if (!cohorts.length) return;
      await api(`/api/v1/training/cohorts/${cohorts[0].id}/enrol`, "POST", {
        workspace_id: currentWsId,
        learner_name: E("trName").value,
        learner_email: E("trEmail").value
      });
      refreshAll();
    }

    async function completeNextModule(enrolmentId, moduleName) {
      await api(`/api/v1/training/enrolments/${enrolmentId}/complete-module`, "POST", {
        module_name: moduleName
      });
      refreshAll();
    }

    async function saveWhiteLabel() {
      await api(`/api/v1/workspaces/${currentWsId}/white-label`, "PUT", {
        is_white_label: true,
        brand_name: E("wlBrand").value,
        custom_domain: E("wlDomain").value,
        primary_color: "#0f172a",
        accent_color: "#2563eb",
        support_email: "support@bidstudio.example",
        client_isolation_enforced: true
      });
      goToWorkspace(currentWsId);
    }

    async function runAccessReview() {
      const res = await api(`/api/v1/workspaces/${currentWsId}/access-review`);
      E("accessReviewOutput").textContent = JSON.stringify(res, null, 2);
    }

    async function createBuyerDraft() {
      await api("/api/v1/public-sector/drafts", "POST", {
        workspace_id: currentWsId,
        authority_name: E("psAuth").value,
        title: E("psTitle").value,
        specification_text: E("psSpec").value,
        evaluation_criteria: [
          { name: "Technical Delivery", weight_pct: 50, max_score: 5, scoring_guidance: "0-5 scale" },
          { name: "Social Value", weight_pct: 20, max_score: 5, scoring_guidance: "0-5 scale" },
          { name: "Price", weight_pct: 30, max_score: 5, scoring_guidance: "Lowest price formula" }
        ]
      });
      refreshAll();
    }

  
document.addEventListener("DOMContentLoaded", () => { loadWorkspaces().then(refreshAll); });

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function createBusinessDoc() {
  const fee = E("bdFee").value;
  if (fee === "" || Number(fee) < 0) { alert("Enter a fixed fee (0 or more). There is no default price."); return; }
  await api("/api/v1/business-docs", "POST", {
    workspace_id: currentWsId,
    doc_type: E("bdType").value,
    title: E("bdTitle").value,
    client_email: E("bdEmail").value,
    fixed_fee: Number(fee)
  });
  refreshAll();
}
async function submitBusinessDocQA(id) { await api(`/api/v1/business-docs/${id}/submit-quality`, "POST"); refreshAll(); }
async function approveBusinessDocQA(id) {
  await api(`/api/v1/business-docs/${id}/review`, "POST", { approved: true, reviewer_notes: "Approved in QA." });
  refreshAll();
}
async function deliverBusinessDoc(id) { await api(`/api/v1/business-docs/${id}/deliver`, "POST"); refreshAll(); }
async function exportBusinessDoc(id) {
  const data = await api(`/api/v1/business-docs/${id}/export`);
  renderMarkdownExport("businessDocsList", "bdExportPreview", `business-doc-${id}.md`, data.markdown);
}

async function createLegalMatter() {
  const fee = E("lgFee").value;
  await api("/api/v1/legal-contracts", "POST", {
    workspace_id: currentWsId,
    contract_type: E("lgType").value,
    title: E("lgTitle").value,
    client_email: E("lgEmail").value,
    jurisdiction: E("lgJurisdiction").value,
    instructions: E("lgInstructions").value,
    quoted_fee: fee === "" ? null : Number(fee)
  });
  refreshAll();
}
// The prompts below stand in for lawyer accounts until the app has real user roles; the API
// records what is entered but cannot verify a lawyer's identity or registration.
async function assignLawyer(id) {
  const name = prompt("Lawyer's full name");
  const ref = name && prompt("Lawyer's registration / practising certificate reference");
  if (!name || !ref) return;
  await api(`/api/v1/legal-contracts/${id}/assign-lawyer`, "POST", { lawyer_name: name, registration_ref: ref });
  refreshAll();
}
function toggleLegalDraft(id) {
  const el = document.getElementById(`lgDraft-${id}`);
  el.style.display = el.style.display === "none" ? "block" : "none";
}
async function saveLegalDraft(id) {
  const name = prompt("Your name (must match the assigned lawyer)");
  if (!name) return;
  await api(`/api/v1/legal-contracts/${id}/draft`, "PUT", { lawyer_name: name, draft_content: document.getElementById(`lgText-${id}`).value });
  refreshAll();
}
async function signOffLegal(id) {
  const name = prompt("Your name (must match the assigned lawyer)");
  if (!name) return;
  const ok = confirm("I confirm I am qualified to practise in this contract's jurisdiction and have reviewed this contract.");
  await api(`/api/v1/legal-contracts/${id}/sign-off`, "POST", { lawyer_name: name, confirm_qualified_and_reviewed: ok });
  refreshAll();
}
async function deliverLegal(id) { await api(`/api/v1/legal-contracts/${id}/deliver`, "POST"); refreshAll(); }
async function exportLegal(id) {
  const data = await api(`/api/v1/legal-contracts/${id}/export`);
  renderMarkdownExport("legalList", "lgExportPreview", `legal-contract-${id}.md`, data.markdown);
}
