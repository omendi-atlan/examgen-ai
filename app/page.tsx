"use client";
import { useCallback, useEffect, useMemo, useState } from "react";

type Question = {
  id:string; section:string; prompt:string;
  type:"multiple_choice"|"dropdown"|"short_answer"|"long_answer"|"numeric";
  marks:number; difficulty:"foundation"|"intermediate"|"advanced";
  options?:string[]; visualDescription?:string;
};
type Exam = { title:string; subject:string; durationMinutes:number; totalMarks:number; instructions:string[]; questions:Question[] };
type QuestionResult = { questionId:string; marksAvailable:number; marksAwarded:number|null; status:string; explanation:string|null };
type Result = { status:string; objectiveScore:number; autoMarkTotal:number; totalMarks:number; pendingReviewCount:number; writtenMarkingNote:string|null; questionResults:QuestionResult[] };

const starterQuestions = [
  {id:"Q1",section:"Section A",prompt:"Which option best describes a project constraint?",type:"multiple_choice",marks:2,difficulty:"foundation",options:["A temporary limitation affecting delivery","A project benefit","A stakeholder title","A project celebration"],answer:"A temporary limitation affecting delivery",explanation:"A constraint limits one or more aspects of project delivery."},
  {id:"Q2",section:"Section B",prompt:"Explain why a project manager should monitor risks throughout a project.",type:"short_answer",marks:3,difficulty:"intermediate",answer:"Risk monitoring identifies changes in exposure and checks whether responses remain effective.",explanation:"Use the rubric to assess the response.",rubric:{criteria:[{criterion:"Identifies changing risk exposure",marks:1,descriptors:{full:"Explains that risks can change over time.",partial:"Mentions changing risks without explanation.",none:"Does not identify changing exposure."}},{criterion:"Explains response effectiveness",marks:1,descriptors:{full:"Explains why controls or responses need review.",partial:"Mentions responses without review.",none:"Does not address responses."}},{criterion:"Connects monitoring to project outcomes",marks:1,descriptors:{full:"Connects monitoring to timely action or project objectives.",partial:"Makes a limited connection.",none:"No relevant connection."}}]}}
];

export default function Home(){
 const apiBase=process.env.NEXT_PUBLIC_EXAMGEN_API_URL;
 const [subject,setSubject]=useState("Project Management");
 const [title,setTitle]=useState("Project Management Practice Examination");
 const [marks,setMarks]=useState(5);
 const [duration,setDuration]=useState(30);
 const [mode,setMode]=useState<"practice"|"simulation">("practice");
 const [difficulty,setDifficulty]=useState<"foundation"|"intermediate"|"advanced">("foundation");
 const [questionsJson,setQuestionsJson]=useState(JSON.stringify(starterQuestions,null,2));
 const [exam,setExam]=useState<Exam|null>(null);
 const [attemptId,setAttemptId]=useState("");
 const [expiresAt,setExpiresAt]=useState("");
 const [remainingSeconds,setRemainingSeconds]=useState(0);
 const [autoSubmitTriggered,setAutoSubmitTriggered]=useState(false);
 const [answers,setAnswers]=useState<Record<string,string>>({});
 const [result,setResult]=useState<Result|null>(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 const timerLabel=`${Math.floor(remainingSeconds/60).toString().padStart(2,"0")}:${(remainingSeconds%60).toString().padStart(2,"0")}`;
 const resultById=useMemo(()=>new Map((result?.questionResults??[]).map(x=>[x.questionId,x])),[result]);

 async function createExam(){
  setBusy(true);setError("");setResult(null);setAttemptId("");setExpiresAt("");setRemainingSeconds(0);setAutoSubmitTriggered(false);setAnswers({});setExam(null);
  try{
   if(!apiBase)throw new Error("The examination API is not configured. Set NEXT_PUBLIC_EXAMGEN_API_URL in GitHub Actions variables and rebuild Pages.");
   let questions:unknown;
   try{questions=JSON.parse(questionsJson)}catch{throw new Error("Questions must be valid JSON. Correct the question editor before continuing.")}
   const examDraft={title,subject,durationMinutes:duration,totalMarks:marks,instructions:["Answer every question. Your responses are saved when you submit."],questions};
   const response=await fetch(`${apiBase.replace(/\/$/,"")}/api/examinations/generate`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mode,exam:examDraft})});
   const payload=await response.json();
   if(!response.ok)throw new Error(payload.error||"The examination could not be created.");
   setAttemptId(payload.attemptId);setExpiresAt(payload.expiresAt);setRemainingSeconds(duration*60);setExam(payload.exam);
  }catch(e){setError(e instanceof Error?e.message:"Examination creation failed.")}finally{setBusy(false)}
 }

 const submit=useCallback(async()=>{
  if(!attemptId||busy||result)return;
  setBusy(true);setError("");
  try{
   const response=await fetch(`${apiBase?.replace(/\/$/,"")}/api/examinations/attempts/submit`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({attemptId,answers})});
   const payload=await response.json();
   if(!response.ok)throw new Error(payload.error||"Submission failed. You can retry.");
   setResult(payload.result);
  }catch(e){setError(e instanceof Error?e.message:"Submission failed. You can retry.")}finally{setBusy(false)}
 },[attemptId,apiBase,answers,busy,result]);

 useEffect(()=>{
  if(!expiresAt||result)return;
  const update=()=>{
   const seconds=Math.max(0,Math.ceil((Date.parse(expiresAt)-120000-Date.now())/1000));
   setRemainingSeconds(seconds);
   if(seconds===0&&!busy&&!autoSubmitTriggered){setAutoSubmitTriggered(true);void submit();}
  };
  update();const timer=window.setInterval(update,1000);return()=>window.clearInterval(timer);
 },[expiresAt,result,busy,autoSubmitTriggered,submit]);

 return <main className="shell">
  <header><div className="brand">EXAMGEN <b>AI</b></div><span className="pill">EXAMINATION WORKSPACE · PROVIDER INDEPENDENT</span></header>
  <section className="hero"><span className="eyebrow">EXAMINATION & LEARNING PLATFORM</span><h1>Build, take and review structured examinations.</h1><p className="muted">Create an examination from authored questions and marking guides. Objective answers are marked automatically; written responses remain pending until assessed against their rubric.</p></section>
  <section className="grid">
   <div className="panel"><span className="eyebrow">01 / EXAMINATION AUTHORING</span><h2>Configure examination</h2>
    <label>Subject or module<input value={subject} onChange={e=>setSubject(e.target.value)}/></label>
    <label>Examination title<input value={title} onChange={e=>setTitle(e.target.value)}/></label>
    <div className="row"><label>Total marks<input type="number" min={1} max={1000} value={marks} onChange={e=>setMarks(+e.target.value)}/></label><label>Duration (minutes)<input type="number" min={1} max={360} value={duration} onChange={e=>setDuration(+e.target.value)}/></label></div>
    <div className="row"><label>Mode<select value={mode} onChange={e=>setMode(e.target.value as "practice"|"simulation")}><option value="practice">Practice</option><option value="simulation">Formal simulation</option></select></label><label>Default difficulty<select value={difficulty} onChange={e=>setDifficulty(e.target.value as typeof difficulty)}><option value="foundation">Foundation</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select></label></div>
    <label>Questions, answer keys and rubrics (JSON)<textarea rows={18} spellCheck={false} value={questionsJson} onChange={e=>setQuestionsJson(e.target.value)}/></label>
    <button className="btn" onClick={createExam} disabled={busy||!subject.trim()||!title.trim()||marks<1||duration<1}>{busy?"Working…":"Create examination →"}</button>
    {error&&<p className="error" role="alert">{error}</p>}
    <p className="muted">The question editor accepts authored questions and marking rubrics. Correct answers, explanations and rubrics are stored server-side and are not returned to the examination page.</p>
   </div>
   <aside className="panel"><span className="eyebrow">ASSESSMENT SNAPSHOT</span><h2>Configuration</h2><div className="stat"><span>Total marks</span><b>{marks}</b></div><div className="stat"><span>Time allowed</span><b>{duration} min</b></div><div className="stat"><span>Mode</span><b>{mode}</b></div><div className="stat"><span>Difficulty setting</span><b>{difficulty}</b></div><p className="muted">The submitted question marks must add up exactly to the configured total. Rubric criteria must also add up to their question's mark allocation.</p></aside>
  </section>
  <section className="panel" style={{marginTop:18}}><span className="eyebrow">02 / EXAMINATION PAPER</span>
   {!exam?<h2>Create an examination to begin</h2>:<>
    <h2>{exam.title}</h2><p className="muted">{exam.subject} · {exam.durationMinutes} minutes · {exam.totalMarks} marks · {mode}</p>
    <div className="stat"><span>Time remaining</span><b aria-live="polite">{timerLabel}</b></div>
    {exam.instructions.map((x,i)=><p className="muted" key={i}>{x}</p>)}
    {exam.questions.map((q,i)=><article className="question" key={q.id}>
     <div className="stat"><span>{q.section} · {q.id}</span><b>{q.marks} marks</b></div><h3>{i+1}. {q.prompt}</h3>
     {q.visualDescription&&<p className="muted">Required visual: {q.visualDescription}</p>}
     {q.type==="dropdown"&&q.options?<select aria-label={`Answer for ${q.id}`} disabled={!!result||remainingSeconds===0} value={answers[q.id]||""} onChange={e=>setAnswers(a=>({...a,[q.id]:e.target.value}))}><option value="">Select an answer…</option>{q.options.map(o=><option key={o} value={o}>{o}</option>)}</select>
     :q.type==="multiple_choice"&&q.options?<div>{q.options.map(o=><label className="option" key={o}><input type="radio" name={q.id} disabled={!!result||remainingSeconds===0} checked={answers[q.id]===o} onChange={()=>setAnswers(a=>({...a,[q.id]:o}))}/>{o}</label>)}</div>
     :q.type==="numeric"?<input className="answer" type="number" aria-label={`Answer for ${q.id}`} disabled={!!result||remainingSeconds===0} value={answers[q.id]||""} onChange={e=>setAnswers(a=>({...a,[q.id]:e.target.value}))}/>
     :<textarea className="answer" rows={q.type==="long_answer"?6:3} aria-label={`Answer for ${q.id}`} disabled={!!result||remainingSeconds===0} value={answers[q.id]||""} onChange={e=>setAnswers(a=>({...a,[q.id]:e.target.value}))} placeholder="Write your answer here…"/>}
     {result&&<p className="muted"><b>{resultById.get(q.id)?.status==="pending_manual_review"?"Pending rubric/manual assessment":`${resultById.get(q.id)?.marksAwarded??0} / ${q.marks} marks`}</b>{resultById.get(q.id)?.explanation?<> · {resultById.get(q.id)?.explanation}</>:null}</p>}
    </article>)}
    {!result?<button className="btn" onClick={submit} disabled={busy}>{busy?"Submitting…":error?"Retry submission":"Submit examination"}</button>
    :<div className="stat"><b>{result.status==="provisional"?"Provisional result":"Marked result"}</b><b>{result.objectiveScore} / {result.autoMarkTotal} objectively marked</b><p className="muted">{result.pendingReviewCount} written response(s) pending human assessment. {result.writtenMarkingNote}</p></div>}
   </>}
  </section>
  <footer className="footer">EXAMGEN AI · Core examination engine · No external AI provider required</footer>
 </main>;
}
