// Golden outputs come exclusively from the supplied JS reference, never Python.
import {writeFileSync} from 'node:fs';
import * as E from './engine.reference.js';

let state=208991;
const random=()=>{state=(Math.imul(1664525,state)+1013904223)>>>0;return state/4294967296;};
const integer=(lo,hi)=>lo+Math.floor(random()*(hi-lo+1));
const scenarios=[];
for(let index=0;index<40;index++){
  const order=E.CRITERIA.slice(index%7).concat(E.CRITERIA.slice(0,index%7)).slice(0,1+index%7);
  const ctx={budgetAnnualPence:integer(100000,300000),bench:{p10:40000,p90:400000},iptRate:.12,
    desiredCoverage:{cancer:{level:3,importance:1,mustHave:index%4===0},mental:{level:integer(1,3),importance:.6},outpatient:{level:integer(1,3),importance:.8}},
    desiredHospitalLevel:integer(1,3),preferredUnderwriting:index%2?'fmu':'moratorium',maxSeverity:10};
  if(index>33)ctx.hardBudgetCapPence=125000;
  if(index>35)ctx.allowedUnderwriting=['moratorium'];
  const plans=Array.from({length:8},(_,j)=>{
    const base=integer(50000,220000);
    return {id:`scenario-${index}-plan-${j}`,insurerId:`insurer-${j%4}`,status:'quoted',basePremiumPence:base,annualPremiumPence:Math.round(base*1.12),
      excessPence:[0,10000,25000,50000][j%4],coverage:{cancer:j===7?2:3,mental:integer(1,3),outpatient:integer(1,3)},hospitalListLevel:integer(1,3),preferredHospitalShare:random(),
      exclusionSeverities:[random()*3],underwritingType:j%2?'fmu':'moratorium',insurerStats:{n:integer(0,300),upheldRate:random()*.6,finStrength:.5+random()*.5,slaScore:random()},
      docsRequired:5,docsUnavailable:integer(0,3),turnaroundDays:integer(1,18),ipidCompleteness:random(),plainLanguage:random(),exclusionsCount:integer(0,15),commissionPct:integer(5,30)};
  });
  if(index%5===0)plans[7].medicalFlagsAmbiguous=true;
  if(index%6===0)plans[6].annualPremiumPence+=1000;
  if(index%7===0)plans[5].status='declined';
  const weights=E.userWeights(order),ranked=E.rankPlans(plans,ctx,weights);
  const sc={order,ctx,plans,weights,ranked,diversified:E.diversify(ranked.rows,5,2).map(r=>r.id)};
  if(ranked.rows.length>=2){
    sc.mc=E.mcStability(ranked.rows,weights,{draws:300,seed:11+index});
    sc.flip=E.flipAnalysis(ranked.rows[0],ranked.rows[1],weights);
    sc.comps=Array.from({length:35},(_,j)=>({better:ranked.rows[(j+1)%ranked.rows.length].u,worse:ranked.rows[j%ranked.rows.length].u,weight:j%2?.5:1}));
    sc.learned=E.learnWeights(weights,sc.comps);sc.shrunk=E.shrinkLearned(weights,sc.learned,sc.comps.length);sc.combined=E.combineWeights(weights,sc.shrunk);
    const extreme=Object.fromEntries(E.CRITERIA.map((c,i)=>[c,i===0?.95:.05/6]));sc.combinedExtreme=E.combineWeights(weights,extreme);
    const ids=ranked.rows.map(r=>r.id);sc.ndcg=E.ndcgAtK(ids,ids.slice(0,3).reverse(),3);sc.ndcg2=E.ndcgAtK(ids,ids.slice(2,5),3);
  }
  scenarios.push(sc);
}
const output={generator:'supplied JS reference; LCG seed 208991; 40 independent contexts',roc:[1,2,3,5,7].map(E.rocWeights),scenarios};
writeFileSync(new URL('./vectors.json',import.meta.url),JSON.stringify(output,null,2)+'\n');
console.log(`Generated ${scenarios.length} JS golden scenarios; ${scenarios.filter(s=>s.mc).length} include MC, flips, learning and caps.`);
