const {build}=require('./package.json');
const fs=require('node:fs');
const config={...build};
const repository=process.env.GITHUB_REPOSITORY;
if(repository) {
 const [owner,repo]=repository.split('/');
 if(!/^[\w-]+$/.test(owner)||!/^[\w.-]+$/.test(repo))throw new Error('Invalid GITHUB_REPOSITORY');
 config.publish={provider:'github',owner,repo,releaseType:'draft'};
 // Build into renderer bundle only after this file is written; see Windows workflow.
}
if(process.env.LOCALCUT_PUBLISHER_NAME)config.win={...config.win,publisherName:process.env.LOCALCUT_PUBLISHER_NAME};
module.exports=config;
