// Dependency-free local adapter: same Worker and schema, persisted in private SQLite.
import {DatabaseSync} from 'node:sqlite';
import {createServer} from 'node:http';
import {readFileSync,existsSync,mkdirSync} from 'node:fs';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import worker from './worker.mjs';
const root=dirname(fileURLToPath(import.meta.url));
mkdirSync(resolve(root,'.local'),{recursive:true});
const db=new DatabaseSync(resolve(root,'.local/state.sqlite3'));
db.exec(readFileSync(resolve(root,'migrations/0001.sql'),'utf8'));
const prepare=sql=>({bind(...args){return {async first(){return db.prepare(sql).get(...args)||null;},async all(){return {results:db.prepare(sql).all(...args)};},async run(){return db.prepare(sql).run(...args);}};},async first(){return db.prepare(sql).get()||null;},async all(){return {results:db.prepare(sql).all()};},async run(){return db.prepare(sql).run();}});
const env={LOCAL:'true',APP_KEY:process.env.FOUNDER_APP_KEY||'morning-local',JOB_TOKEN:process.env.FOUNDER_JOB_TOKEN||'local-job-only',DB:{prepare,async batch(statements){db.exec('BEGIN');try{for(const s of statements)await s.run();db.exec('COMMIT');}catch(e){db.exec('ROLLBACK');throw e;}}},ASSETS:{async fetch(req){let pathname=decodeURIComponent(new URL(req.url).pathname);if(pathname==='/')pathname='/index.html';const base=resolve(root,'public'),file=resolve(base,'.'+pathname);if(!file.startsWith(base+'\\')&&!file.startsWith(base+'/'))return new Response('Not found',{status:404});try{return new Response(readFileSync(file),{headers:{'content-type':({'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.svg':'image/svg+xml'})[extname(file)]||'application/octet-stream','cache-control':'no-store'}});}catch{return new Response('Not found',{status:404});}}}};
const input=resolve(root,'.local/issue.json');
if(existsSync(input)) {
 const issue=JSON.parse(readFileSync(input,'utf8'));
 const response=await worker.fetch(new Request('http://localhost/internal/issues',{method:'POST',headers:{authorization:'Bearer '+env.JOB_TOKEN},body:JSON.stringify(issue)}),env);
 if(!response.ok)throw new Error('Local import failed');
}
createServer(async(req,res)=>{try{const chunks=[];for await(const chunk of req)chunks.push(chunk);const response=await worker.fetch(new Request('http://127.0.0.1:8787'+req.url,{method:req.method,headers:req.headers,...(['GET','HEAD'].includes(req.method)?{}:{body:Buffer.concat(chunks)})}),env);res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));}catch{res.writeHead(500);res.end('Local server error');}}).listen(8787,'127.0.0.1',()=>console.log('Founder Morning: http://127.0.0.1:8787 — local login: morning-local (unless overridden). No cloud or Telegram connections.'));
