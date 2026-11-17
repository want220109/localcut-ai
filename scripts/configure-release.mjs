import fs from 'node:fs/promises';
const repository=process.env.GITHUB_REPOSITORY;
if(!repository)throw new Error('GITHUB_REPOSITORY must be owner/repository');
const [owner,repo]=repository.split('/');
if(!/^[A-Za-z0-9-]+$/.test(owner)||!/^[A-Za-z0-9_.-]+$/.test(repo))throw new Error('Invalid repository');
await fs.writeFile('updater/config.json',JSON.stringify({owner,repo})+'\n');
console.log('Update feed configured for',repository);
