O **Sócrates Tênis** é um sistema construído em blocos, com foco em organização, escalabilidade e evolução gradual.

A proposta é criar uma base sólida para controlar regras de negócio relacionadas a:

- cadastro de usuários;
- autenticação;
- professores;
- alunos;
- quadras;
- aulas;
- agendamentos;
- disponibilidade de horários;
- regras administrativas;
- integrações futuras.

O backend foi pensado para ser desenvolvido de forma modular, permitindo que novas funcionalidades sejam adicionadas sem comprometer a estrutura principal do sistema.

---

## Objetivo do backend

Este backend é responsável por concentrar as regras de negócio e a comunicação entre o frontend, o banco de dados e os serviços internos da aplicação.

Entre suas responsabilidades estão:

- processar requisições da aplicação;
- validar dados recebidos;
- aplicar regras de negócio;
- controlar autenticação e permissões;
- consultar e persistir informações no banco de dados;
- disponibilizar endpoints para consumo pelo frontend;
- organizar a evolução do sistema por módulos.

---

## Tecnologias utilizadas

As tecnologias podem evoluir conforme o avanço do projeto, mas a base do backend contempla:

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- JWT para autenticação
- Alembic / migrations
- Estrutura modular por rotas, controllers, models e serviços

---

## Estrutura esperada do projeto

A estrutura pode variar conforme a evolução do sistema, mas a organização segue uma ideia modular:

```text
SocratesTenis_BackEnd/
├── app/
│   ├── models/
│   ├── routes/
│   ├── services/
│   ├── schemas/
│   ├── utils/
│   └── __init__.py
├── migrations/
├── tests/
├── main.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## Principais módulos

### Autenticação

Responsável pelo controle de login, validação de usuário e geração de tokens de acesso.

### Usuários

Base para cadastro e controle de diferentes perfis dentro do sistema, como administradores, professores e alunos.

### Professores

Módulo voltado ao gerenciamento de professores, disponibilidade e vínculo com aulas ou horários.

### Alunos

Módulo responsável pelas informações dos alunos e possíveis vínculos com aulas, agendamentos e histórico.

### Quadras

Controle das quadras disponíveis, incluindo regras relacionadas a horários, reservas e disponibilidade.

### Agendamentos

Módulo central para controle das reservas, aulas e horários disponíveis dentro da operação.

---

## Regras de negócio

O sistema está sendo construído com atenção às regras específicas de uma operação real de tênis.

Alguns exemplos de regras previstas ou em evolução:

- controle de horários disponíveis;
- separação entre aulas e locação de quadra;
- tratamento específico para aulas grátis;
- controle de permissões por tipo de usuário;
- validação de conflitos de agenda;
- preparação para regras futuras, como contratação opcional de catador;
- evolução por migrations para manter consistência entre ambiente local e servidor.

---

## Status do projeto

Projeto em desenvolvimento.

O backend está sendo construído de forma incremental, priorizando uma base segura, organizada e preparada para evolução.
