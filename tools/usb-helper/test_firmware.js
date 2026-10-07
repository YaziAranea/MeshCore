'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {createHash,webcrypto} = require('node:crypto');
const {verify,PROFILES,reportedProfile} = require('./firmware.js');
const COMMIT = '12345678' + 'a'.repeat(32);
const VERSION = '0.14';
const sha = data => createHash('sha256').update(data).digest('hex');

function application(profile, source = COMMIT.slice(0,8), appendedHash = true, version = VERSION) {
  const payload = Buffer.from(profile.marker + ' SmartUI ' + version + '\0SmartUI-source:' + source + '\0','utf8');
  const end = Math.floor((32 + payload.length + 16)/16)*16;
  const app = Buffer.alloc(end + (appendedHash ? 32 : 0));
  app[0] = 0xe9; app[1] = 1; app[23] = appendedHash ? 1 : 0;
  app.writeUInt32LE(0x40080000,24); app.writeUInt32LE(payload.length,28); payload.copy(app,32);
  let checksum = 0xef; for (const byte of payload) checksum ^= byte;
  app[end-1] = checksum;
  if(appendedHash) Buffer.from(sha(app.subarray(0,end)),'hex').copy(app,end);
  return app;
}
function uf2(profile, version = VERSION) {
  const payload = Buffer.alloc(512);
  Buffer.from(profile.marker + ' SmartUI ' + version + '\0').copy(payload,0);
  Buffer.from('SmartUI-source:' + COMMIT.slice(0,8) + '\0').copy(payload,248);
  const raw = Buffer.alloc(1024);
  for(let index=0;index<2;++index) {
    const block = raw.subarray(index*512,(index+1)*512);
    [0x0a324655,0x9e5d5157,0x2000,0x26000+index*256,256,index,2,0xada52840].forEach((value,i)=>block.writeUInt32LE(value,i*4));
    payload.copy(block,32,index*256,(index+1)*256); block.writeUInt32LE(0x0ab16f30,508);
  }
  return raw;
}
function fixture(id='v3', merged=false, source, version=VERSION) {
  const profile = PROFILES.find(p=>p.id===id);
  let bytes;
  if(profile.format==='uf2') bytes=uf2(profile,version);
  else {
    const app=application(profile,source,true,version);
    bytes=merged?Buffer.alloc(0x10000+app.length+256,0xff):app;
    if(merged) {bytes[0]=0xe9;app.copy(bytes,0x10000);}
  }
  const name = profile.id + (profile.format==='uf2'?'.uf2':merged?'-merged.bin':'-update.bin');
  const record = {name,bytes:bytes.length,sha256:sha(bytes),board:profile.label,environment:profile.environment,source_commit:COMMIT,image_kind:profile.format==='uf2'?'nrf52840-uf2-bootloader':merged?'esp32-fresh-install-merged':'esp32-application-update',flash_offset:profile.format==='uf2'?null:merged?'0x00000':'0x10000'};
  const manifest = {schema_version:2,commit:COMMIT,version,firmware:[record]};
  return {profile,bytes,name,record,manifest, args(){return {name,bytes:this.bytes,manifestText:JSON.stringify(manifest),target:id,cryptoProvider:webcrypto};}};
}

test('preflight validates all seven profiles and reconstructs split UF2 markers', async()=>{
  assert.equal(PROFILES.length,7);
  for(const profile of PROFILES) {
    const f=fixture(profile.id);
    const result=await verify({...f.args(),info:{board:profile.reported,build:COMMIT.slice(0,8)}});
    assert.equal(result.board,profile.label);assert.equal(result.matchedConnectedBoard,true);assert.equal(result.sameBuild,true);
    assert.match(result.integrityNotice,/не подлинность|а не подлинность/);
  }
});

test('preflight retains 0.09 through 0.12 release compatibility for all six profiles', async()=>{
  const legacyProfiles=PROFILES.filter(profile=>profile.id!=='v4r8');
  assert.equal(legacyProfiles.length,6);
  for(const version of ['0.09','0.10','0.11','0.12']) for(const profile of legacyProfiles) {
    const result=await verify(fixture(profile.id,false,undefined,version).args());
    assert.equal(result.board,profile.label);
  }
});
test('V4 R8 starts with 0.13 and remains distinct from ordinary V4.3 R2',async()=>{
  const r8=PROFILES.find(profile=>profile.id==='v4r8');
  assert.equal(r8.environment,'heltec_v4_r8_companion_radio_ble_femon_smartui');
  assert.equal(r8.marker+' SmartUI '+VERSION,'V4 R8 SmartUI 0.14');
  assert.equal(reportedProfile({board:'Heltec V4 R8 OLED'}),r8);
  assert.equal(reportedProfile({board:'Heltec V4.3 OLED'}).id,'v43');
  assert.equal(reportedProfile({board:'Heltec V4 R8 TFT'}),null);
  for(const version of ['0.09','0.10','0.11','0.12','unknown']) {
    await assert.rejects(verify(fixture('v4r8',false,undefined,version).args()),/не поддерживается/);
  }
  for(const version of ['0.13','0.14','1.0']) {
    assert.equal((await verify(fixture('v4r8',false,undefined,version).args())).board,r8.label);
  }
  for(const [id,other] of [['v4r8','v43'],['v43','v4r8']]) for(const merged of [false,true]) {
    const f=fixture(id,merged);
    const otherProfile=PROFILES.find(profile=>profile.id===other);
    await assert.rejects(verify({...f.args(),target:other}),/другой платы/);
    await assert.rejects(verify({...f.args(),info:{board:otherProfile.reported}}),/другой платы/);
    // A matching filename and manifest cannot relabel the embedded board marker.
    f.record.board=otherProfile.label;f.record.environment=otherProfile.environment;
    await assert.rejects(verify({...f.args(),target:other}),/платы\/версии/);
  }
});
test('merged and update carry different explicit warnings, offsets and manual-model scope',async()=>{
  for(const id of ['v3','v43','v4r8','paper']) {
    const fresh=await verify(fixture(id,true).args());
    assert.equal(fresh.destructive,true);assert.equal(fresh.offset,'0x00000');assert.match(fresh.warning,/даже без Erase/);
    const update=await verify(fixture(id).args());assert.equal(update.offset,'0x10000');assert.match(update.warning,/bootloader/);assert.equal(update.matchedConnectedBoard,false);
  }
});
test('reject wrong board, unknown model, hash mismatch, duplicate records and hostile metadata',async()=>{
  const f=fixture();
  await assert.rejects(verify({...f.args(),target:'t114'}),/другой платы/);
  await assert.rejects(verify({...f.args(),info:{board:'Heltec T114'}}),/другой платы/);
  await assert.rejects(verify({...f.args(),target:'',info:{board:'unknown'}}),/неизвестна/);
  await assert.rejects(verify({...f.args(),manifestText:'<script>'}),/JSON/);
  f.record.sha256='0'.repeat(64);await assert.rejects(verify(f.args()),/SHA-256/);f.record.sha256=sha(f.bytes);
  f.manifest.firmware.push({...f.record});await assert.rejects(verify(f.args()),/несколько/);f.manifest.firmware.pop();
  f.record.board='<img>';await assert.rejects(verify(f.args()),/Плата/);
});
test('reject dirty source, wrong source and mismatched embedded board/version',async()=>{
  for(const source of ['12345678+dirty','ffffffff','unknown']) await assert.rejects(verify(fixture('v3',false,source).args()),/source marker/);
  const f=fixture();f.manifest.version=VERSION+'-mismatch';await assert.rejects(verify(f.args()),/платы\/версии/);
});
test('reject BIN structural corruption and update with trailing filesystem bytes even with matching file hash',async()=>{
  for(const change of [f=>f.bytes[0]=0,f=>f.bytes[1]=17,f=>f.bytes.writeUInt32LE(0xffffffff,28),f=>f.bytes[32]^=1,f=>f.bytes[f.bytes.length-1]^=1,f=>{f.bytes=Buffer.concat([f.bytes,Buffer.alloc(16)]);}]) {
    const f=fixture();change(f);f.record.bytes=f.bytes.length;f.record.sha256=sha(f.bytes);await assert.rejects(verify(f.args()));
  }
  const f=fixture();f.record.flash_offset='0x00000';await assert.rejects(verify(f.args()),/противоречат/);
});
test('reject malformed UF2 layout/family/flags/count with otherwise matching manifest hash',async()=>{
  for(const [offset,value] of [[0,0],[8,0],[12,0],[16,512],[20,1],[24,3],[28,0],[508,0],[512+12,0x26000]]) {
    const f=fixture('t114');f.bytes.writeUInt32LE(value,offset);f.record.sha256=sha(f.bytes);await assert.rejects(verify(f.args()));
  }
});
test('preflight bounds input and fails closed without local digest capability',async()=>{
  const f=fixture();await assert.rejects(verify({...f.args(),cryptoProvider:null}),/SHA-256/);
  await assert.rejects(verify({...f.args(),bytes:new Uint8Array(0)}),/непустой/);
  await assert.rejects(verify({...f.args(),manifestText:' '.repeat(2*1024*1024+1)}),/2 МиБ/);
  await assert.rejects(verify({...f.args(),name:'../v3-update.bin'}),/Имя/);
});
