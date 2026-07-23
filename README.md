SIGALI — Sistema Inteligente de Gestão da Agenda Legislativa da Indústria
Painel para acompanhamento do cronograma da Agenda Legislativa da Indústria (ALI): cadastro de
atividades e responsáveis, indicadores de execução, alertas de prazo e visão consolidada para o
Diretor. Desenvolvido para a Confederação Nacional da Indústria.
Versão auto-hospedada (gratuita)
Este pacote é a versão do SIGALI que roda fora do Claude, sem depender de link
de artefato nem de aprovação de TI. Tudo gratuito. Você não precisa programar —
só criar 3 ou 4 contas gratuitas e colar algumas informações onde indicado.
O que você vai criar (todas gratuitas)
Conta	Para que serve
Supabase	O banco de dados — guarda o cronograma, responsáveis e marcos
GitHub	Guarda o código e roda o robô de alertas diários
Streamlit Community Cloud	Hospeda o painel (o "site" do SIGALI)
Telegram (opcional, recomendado)	Canal de alerta instantâneo, mais fácil de automatizar que WhatsApp
Passo 1 — Banco de dados (Supabase)
Crie uma conta gratuita em supabase.com e um novo projeto (escolha uma senha e guarde-a).
No menu lateral, abra SQL Editor → New query.
Copie todo o conteúdo do arquivo `schema.sql` (está nesta mesma pasta) e cole ali. Clique em Run.
Isso cria as tabelas e já carrega as 204 atividades reais, os 28 responsáveis e os 15 marcos importados da planilha.
Vá em Project Settings → API. Copie a Project URL e a chave anon public — você vai usar as duas no Passo 3.
Passo 2 — Subir o código para o GitHub
Crie um repositório novo (pode ser privado) no GitHub.
Envie todos os arquivos desta pasta (`app.py`, `requirements.txt`, `schema.sql`, a pasta `.streamlit`, `scripts` e `.github`) para esse repositório.
Se nunca usou Git: no GitHub, use o botão "Add file" → "Upload files" e arraste tudo — não precisa linha de comando.
Passo 3 — Publicar o painel (Streamlit Community Cloud)
Crie uma conta gratuita em streamlit.io/cloud, entrando com sua conta GitHub.
Clique em "New app", escolha o repositório que você acabou de criar, e o arquivo principal `app.py`.
Antes de clicar em "Deploy", vá em "Advanced settings" → "Secrets" e cole:
```
   supabase_url = "COLE_A_PROJECT_URL_AQUI"
   supabase_key = "COLE_A_CHAVE_ANON_AQUI"
   admin_pin = "sigali2027"
   ```
(troque `sigali2027` pelo PIN que você quiser usar para entrar como administrador)
Clique em Deploy. Em 1–2 minutos, o Streamlit te dá o link do painel — esse é o link que você manda para a equipe.
Já tenho o sistema rodando — e ano que vem, com a agenda nova?
Se você já publicou o SIGALI seguindo os passos acima, rode esta migração uma vez só para
habilitar múltiplos ciclos (ex.: ALI 2027, ALI 2028, ...):
No Supabase, vá em SQL Editor → cole o conteúdo do arquivo `migracao_ciclos.sql` (está
nesta pasta) → Run.
Vá no repositório do GitHub, abra `app.py`, clique no lápis de editar, apague todo o conteúdo
e cole o `app.py` atualizado deste zip → Commit changes. O Streamlit atualiza sozinho.
A partir daí, um seletor "Ciclo / Agenda" aparece na barra lateral do painel — a ALI 2027
continua toda guardada ali.
Quando chegar a agenda de um novo ano: entre como administrador, vá na aba Cronograma,
abra a seção "📥 Importar nova agenda (novo ciclo)", dê um nome ao ciclo (ex.: `ALI 2028`) e
suba a planilha nova (mesmo modelo da Matriz RACI). O sistema lê, mostra uma prévia das atividades
antes de gravar, e depois de confirmar, o ciclo novo já aparece no seletor — sem precisar mexer em
código nem voltar a falar comigo, a não ser que a planilha venha num formato bem diferente do atual.
Passo 4 — Alertas automáticos diários (opcional, mas é o que você pediu)
Isso usa o GitHub Actions para rodar um robô todo dia de manhã, sem precisar de servidor.
No repositório do GitHub, vá em Settings → Secrets and variables → Actions → New repository secret e cadastre, um de cada vez:
`SUPABASE_URL` e `SUPABASE_KEY` (os mesmos do Passo 1)
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` — dados de um e-mail para enviar os alertas. Com Gmail: `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER` é o e-mail, `SMTP_PASS` é uma "senha de app" (não é a senha normal da conta).
`TELEGRAM_BOT_TOKEN` (opcional) — veja abaixo como conseguir.
Na aba Responsáveis do SIGALI, preencha o e-mail de cada pessoa (e o `telegram_chat_id`, se for usar Telegram).
Pronto — o robô roda sozinho todo dia às 8h (horário de Brasília). Para testar na hora, vá na aba Actions do GitHub e rode manualmente o workflow "SIGALI - alertas diários".
Como conseguir o Telegram Bot Token
No Telegram, converse com o usuário @BotFather e mande `/newbot`, seguindo as instruções.
Ele te devolve um token — esse é o `TELEGRAM_BOT_TOKEN`.
Cada pessoa da equipe precisa mandar uma mensagem qualquer para o bot uma vez, e depois abrir `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates` no navegador para descobrir o próprio `chat_id` — cole esse número na aba Responsáveis do SIGALI.
Sobre WhatsApp — leia antes de prometer isso à equipe
Não existe hoje uma forma gratuita e simples de automatizar WhatsApp para várias pessoas de uma vez.
A opção gratuita que existe (CallMeBot) exige que cada pessoa individualmente mande uma mensagem para
um número específico para gerar sua própria chave (`apikey`), e tem limite de mensagens por dia. Para uma
equipe inteira, o Telegram é muito mais confiável e não tem esse atrito — considere usá-lo como o canal
"instantâneo" no lugar do WhatsApp, ou como complemento para quem topar configurar.
Se ainda assim quiser WhatsApp via CallMeBot: peça para a pessoa mandar "I allow callmebot to send me messages"
para o número +34 644 51 95 23 no WhatsApp, aguardar a resposta com a apikey, e colar o número e a apikey
na aba Responsáveis (`whatsapp` e `callmebot_apikey`).
Painel: administrador x colaborador
Qualquer pessoa que abrir o link do painel entra como colaborador (só consulta).
Para editar, clique em "Entrar como administrador" na barra lateral e digite o PIN definido no Passo 3.
Assim como na versão anterior, isso não é uma segurança real — é uma trava de conveniência. Qualquer
pessoa com o PIN vira administrador.
Dúvidas frequentes
Preciso saber programar para manter isso? Não. No dia a dia, você só usa o painel do SIGALI
(as tabelas dá para editar direto na tela, como uma planilha). Só volta a mexer no código se quiser
mudar alguma regra de funcionamento — aí é só voltar a conversar comigo.
E se eu errar algo na hora de subir os arquivos? Sem problema, me chama de volta com o que
aconteceu e eu te ajudo a corrigir.
