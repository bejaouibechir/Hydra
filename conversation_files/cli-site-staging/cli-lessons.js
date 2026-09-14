/* Source unique des ateliers de la piste CLI.
   Consommee par /cli (carte du cours) et par chaque page de lecon sous /cli/.

   `label`  : intitule court, menu de gauche.
   `title`  : intitule complet, carte de droite et titre de la lecon.
   `group`  : le module auquel l'atelier appartient.
   `command`: la commande exacte sur laquelle l'atelier se joue.
   `slug`   : la route servie sous /cli/. `null` tant que la lecon n'est pas ecrite —
              la carte reste alors inerte et porte la mention Outline. */

export const cliLessons = [
  { slug: '01-install-and-verify',
    label: 'Install',          group: 'Install and verify',  command: 'hdrctl --help',
    title: 'Install and verify',
    description: 'Install Hydra, find the CLI entry point and confirm the active version.' },

  { slug: '02-scaffold-your-first-job',
    label: 'Create a job',     group: 'Create a job',         command: 'hdrctl init',
    title: 'Scaffold your first job',
    description: 'Create the project and read the files the template just produced.' },

  { slug: '03-validate-the-manifests',
    label: 'Validate',         group: 'Validate before I/O',  command: 'hdrctl validate',
    title: 'Check the manifests before touching data',
    description: 'Separate a declaration error from an execution error, before anything is written.' },

  { slug: '04-test-the-connections',
    label: 'Test connections', group: 'Validate before I/O',  command: 'hdrctl test',
    title: 'Prove the connection exists',
    description: 'Confirm source and destination access without producing a single row.' },

  { slug: '05-run-the-job',
    label: 'Run a job',        group: 'Run and inspect',      command: 'hdrctl run',
    title: 'Run the job and read the evidence',
    description: 'Execute, read the counters and locate the file the run produced.' },

  { slug: '06-read-the-output',
    label: 'Read the output',  group: 'Run and inspect',      command: 'hdrctl run -vv',
    title: 'Turn up the verbosity when something is unclear',
    description: 'Move from a one-line summary to a step-by-step log of the same run.' },

  { slug: '07-pass-parameters',
    label: 'Pass parameters',  group: 'Run and inspect',      command: 'hdrctl run -P',
    title: 'Change one value without touching the YAML',
    description: 'Replay the same job on another scope by overriding a parameter at run time.' },

  { slug: '08-list-the-project',
    label: 'List the project', group: 'Run and inspect',      command: 'hdrctl list',
    title: 'Ask the project what it contains',
    description: 'Inventory the declared sources and destinations without opening a file.' },

  { slug: '09-build-a-workflow',
    label: 'Build a workflow', group: 'Operate workflows',    command: 'hdrctl workflow',
    title: 'Compose your jobs into a workflow',
    description: 'Declare dependencies between jobs and validate the whole before running it.' },

  { slug: '10-run-a-workflow',
    label: 'Run a workflow',   group: 'Operate workflows',    command: 'hdrctl workflow run',
    title: 'Run the workflow and follow every state',
    description: 'Read one terminal state per step, then replay only what needs replaying.' },

  { slug: '11-serve-the-api',
    label: 'Serve the API',    group: 'Serve Hydra',          command: 'hdrctl serve',
    title: 'Serve Hydra for Studio and the API',
    description: 'Start the backend on a workspace so Studio and the API share the same project.' }
];

export default cliLessons;
