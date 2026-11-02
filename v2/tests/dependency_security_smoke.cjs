const {createRequire}=require('module');
const path=require('path');
const assert=require('assert/strict');
const {PassThrough}=require('stream');
const zlib=require('zlib');
const base=path.resolve(process.argv[2]);
const req=createRequire(path.join(base,'package.json'));
(async()=>{
 const uri=req('fast-uri');
 assert.equal(uri.resolve('https://example.invalid/a/b','../c'),'https://example.invalid/c');
 assert.equal(uri.parse('https://example.invalid/path').host,'example.invalid');
 assert(!/^javascript:/i.test(uri.normalize('%6Aavascript:alert(1)')));
 const Ajv=req('ajv');const ajv=new Ajv();const validate=ajv.compile({type:'object',properties:{message:{type:'string'}},required:['message'],additionalProperties:false});assert(validate({message:'ok'}));assert(!validate({message:1}));
 const bodyParser=req('body-parser');
 async function parse(trailing){
  let uncaught=[];const listener=e=>uncaught.push(e.code||e.name);process.on('uncaughtException',listener);
  const compressed=zlib.gzipSync(Buffer.from('{"message":"ok"}'));const payload=Buffer.concat([compressed,trailing?Buffer.from('trailing bytes'):Buffer.alloc(0)]);
  const stream=new PassThrough();stream.headers={'content-type':'application/json','content-encoding':'gzip','content-length':String(payload.length)};stream.method='POST';
  const outcome=await new Promise(resolve=>{bodyParser.json()(stream,{},error=>resolve({error:error?error.type:null,body:stream.body}));stream.end(payload)});
  await new Promise(resolve=>setTimeout(resolve,100));process.removeListener('uncaughtException',listener);assert.deepEqual(uncaught,[]);if(!trailing)assert.deepEqual(outcome.body,{message:'ok'});return outcome.error;
 }
 await parse(false);const compressedError=await parse(true);
 const {pathToFileURL}=require('url');const load=p=>import(pathToFileURL(req.resolve(p)).href);
 const {Client}=await load('@modelcontextprotocol/sdk/client/index.js');const {Server}=await load('@modelcontextprotocol/sdk/server/index.js');const {InMemoryTransport}=await load('@modelcontextprotocol/sdk/inMemory.js');
 const [a,b]=InMemoryTransport.createLinkedPair();const client=new Client({name:'flow-dependency-smoke',version:'1.0.0'});const server=new Server({name:'flow-peer-sdk',version:'1.0.0'},{capabilities:{}});await Promise.all([server.connect(b),client.connect(a)]);assert.equal(client.getServerVersion().name,'flow-peer-sdk');await client.close();await server.close();
 console.log(JSON.stringify({uri:'passed',ajv:'passed',compressedBody:'passed',trailingCompressedBody:compressedError||'no uncaught exception',mcpInMemoryHandshake:'passed',networkListener:false}));
})().catch(e=>{console.error(e);process.exitCode=1});
