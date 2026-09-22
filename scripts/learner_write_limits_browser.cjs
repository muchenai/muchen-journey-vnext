const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const api = process.env.RATE_TEST_API || 'http://127.0.0.1:58049';
const web = process.env.RATE_TEST_WEB || 'http://127.0.0.1:5309';
for (const url of [api, web]) assert.equal(new URL(url).hostname, '127.0.0.1', 'Synthetic burst tests require loopback-only targets');
(async () => {
 const browser = await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,headless:true});
 try {
 const ctx = await browser.newContext({viewport:{width:1280,height:900}});
 const req = ctx.request;
 async function call(path, data, headers={}) {
   const r = await req.post(api+path,{data,headers:{'Idempotency-Key':crypto.randomUUID(),...headers}});
   assert(r.ok(),`${path}: ${r.status()} ${await r.text()}`);return (await r.json()).data;
 }
 const invite = await call('/api/v1/ops/invites',{purpose:'Synthetic local rate-limit browser check',expires_in_hours:1,role:'LEARNER',reviewer_id:'10000000-0000-4000-8000-000000000003',task_version_id:'10000000-0000-4000-8000-00000000000c',target_user_id:null},{'X-Fixture-Role':'OPERATOR'});
 const exchange = await call('/api/v1/join/exchange',{token:invite.invite_token,return_to:'/app'});
 const confirmed = await call('/api/v1/identity/confirm',{display_name:'Synthetic limit browser',accepted_purpose:true,return_to:'/app'},{'X-CSRF-Token':exchange.csrf_token});
 const current = (await (await req.get(api+'/api/v1/me/current-action')).json()).data;
 const headers = {'X-CSRF-Token':confirmed.csrf_token};
 const start = await call(`/api/v1/me/assignments/${current.resource_id}/start`,{expected_revision:current.revision},headers);
 const path = `/api/v1/me/assignments/${current.resource_id}/draft`;
 const page = await ctx.newPage(); const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(web+`/app/tasks/${current.resource_id}`,{waitUntil:'networkidle'});
 const body=page.locator('textarea[name="body"]'); await body.waitFor();
 // Fill the server's minute bucket before the UI autosave, without using a real identity.
 await Promise.all(Array.from({length:95},(_,i)=>req.put(api+path,{headers:{...headers,'Idempotency-Key':crypto.randomUUID()},data:{expected_revision:start.revision,body:'Synthetic burst '+i}})));
 await body.fill('合成浏览器测试正文'.repeat(8));
 await page.getByText(/保存过于频繁，请等待 \d+ 秒；当前输入已保留/).waitFor({timeout:20000});
 assert(await page.getByRole('button',{name:'保存草稿',exact:true}).isDisabled());
 const latest='限流期间继续编辑的最新正文'.repeat(8); await body.fill(latest);
 if (process.env.RATE_TEST_SCREENSHOTS) await page.screenshot({path:process.env.RATE_TEST_SCREENSHOTS+'/desktop.png'});
 await page.setViewportSize({width:390,height:844});
 if (process.env.RATE_TEST_SCREENSHOTS) await page.screenshot({path:process.env.RATE_TEST_SCREENSHOTS+'/mobile.png'});
 await page.setViewportSize({width:768,height:1024});
 if (process.env.RATE_TEST_SCREENSHOTS) await page.screenshot({path:process.env.RATE_TEST_SCREENSHOTS+'/tablet.png'});
 await page.getByText(/保存过于频繁，请等待 \d+ 秒；当前输入已保留/).waitFor({state:'hidden',timeout:70000});
 await page.waitForTimeout(2500);
 const detail=(await(await req.get(api+`/api/v1/me/assignments/${current.resource_id}`)).json()).data;
 assert.equal(detail.draft.body,latest); assert.equal(await body.inputValue(),latest);
 // Submit allowance is independent. Consume it with valid commands targeting a
 // nonexistent assignment: business failures must not refund the counter.
 await page.getByRole('button',{name:'检查并提交',exact:true}).click();
 const key=await page.locator('input[name="submission_idempotency_key"]').inputValue();
 await Promise.all(Array.from({length:25},()=>req.post(api+`/api/v1/me/assignments/${crypto.randomUUID()}/submissions`,{headers:{...headers,'Idempotency-Key':crypto.randomUUID()},data:{expected_revision:1,body:latest}})));
 await page.getByRole('button',{name:'确认正式提交',exact:true}).click();
 const notice=page.getByText(/提交过于频繁，请等待 \d+ 秒后再次确认/);
 await notice.waitFor({timeout:20000});
 assert(await page.getByRole('button',{name:'确认正式提交',exact:true}).isDisabled());
 assert.equal(await page.locator('input[name="submission_idempotency_key"]').inputValue(),key);
 await notice.waitFor({state:'hidden',timeout:70000});
 await page.waitForTimeout(1000);
 assert.equal(await page.locator('input[name="submission_idempotency_key"]').inputValue(),key);
 assert(await page.getByRole('button',{name:'确认正式提交',exact:true}).isEnabled());
 const beforeSubmit=(await(await req.get(api+`/api/v1/me/assignments/${current.resource_id}`)).json()).data;
 assert.equal(beforeSubmit.submission,null);
 await page.getByRole('button',{name:'确认正式提交',exact:true}).click();
 await page.waitForTimeout(3500);
 const afterSubmit=(await(await req.get(api+`/api/v1/me/assignments/${current.resource_id}`)).json()).data;
 assert.equal(afterSubmit.submission.current_version_no,1);
 assert.equal(afterSubmit.submission.versions.length,1);
 assert.equal(errors.length,0,JSON.stringify(errors));
 console.log(JSON.stringify({result:'PASS',url:page.url(),title:await page.title(),draftCooldown:true,latestDraftRecovered:true,submitCooldown:true,manualRetryOnly:true,oneVersion:true,pageErrors:errors}));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
