// Curated catalog of 3D model marketplaces and free-model communities.
// Used by /projects. Order roughly: largest free-first communities, then
// premium / niche.

export type Tier = "free" | "freemium" | "paid";
export type SiteCategory =
  | "community"
  | "marketplace"
  | "engineering"
  | "render";

export type ProjectSite = {
  slug: string;
  name: string;
  url: string;
  tagline: string;
  description: string;
  tier: Tier;
  category: SiteCategory;
  ecosystem?: string; // associated printer brand / parent
  highlights: string[];
};

export const PROJECT_SITES: ProjectSite[] = [
  {
    slug: "printables",
    name: "Printables",
    url: "https://www.printables.com",
    tagline: "Comunidade da Prusa, foco em qualidade.",
    description:
      "Maior comunidade ativa hoje. Filtros de licença, gcode pré-fatiado pra Prusa e remix tracking. Tudo grátis.",
    tier: "free",
    category: "community",
    ecosystem: "Prusa Research",
    highlights: ["100% grátis", "Concursos mensais", "Licenças explícitas"],
  },
  {
    slug: "makerworld",
    name: "MakerWorld",
    url: "https://makerworld.com",
    tagline: "Plataforma oficial da Bambu Lab.",
    description:
      "Crescimento acelerado. Modelos otimizados pra Bambu A/P/X, suporte a multi-color builtin, sistema de pontos pra criadores.",
    tier: "free",
    category: "community",
    ecosystem: "Bambu Lab",
    highlights: ["AMS multi-color nativo", "Print profiles oficiais", "Sistema de pontos"],
  },
  {
    slug: "thingiverse",
    name: "Thingiverse",
    url: "https://www.thingiverse.com",
    tagline: "O clássico do MakerBot/UltiMaker.",
    description:
      "O maior acervo histórico — mais de 2 milhões de modelos. Interface envelhecida e moderação fraca, mas ainda é referência absoluta.",
    tier: "free",
    category: "community",
    ecosystem: "UltiMaker",
    highlights: ["Catálogo gigante", "Customizer", "Tudo grátis"],
  },
  {
    slug: "cults3d",
    name: "Cults3D",
    url: "https://cults3d.com",
    tagline: "Marketplace francês com curadoria.",
    description:
      "Mistura grátis + pago. Curadoria editorial, foco em designs com apelo comercial (cosplay, decoração, miniaturas).",
    tier: "freemium",
    category: "marketplace",
    highlights: ["Curadoria editorial", "Pagamento direto ao designer", "Categorias premium"],
  },
  {
    slug: "thangs",
    name: "Thangs",
    url: "https://thangs.com",
    tagline: "Busca geométrica entre todos os sites.",
    description:
      "Engine de busca que indexa Printables, Thingiverse, Cults, MakerWorld e mais. Search por similaridade geométrica — você sobe um STL e ele acha modelos parecidos.",
    tier: "free",
    category: "community",
    highlights: ["Indexa vários sites", "Busca por geometria", "Versionamento Git-like"],
  },
  {
    slug: "myminifactory",
    name: "MyMiniFactory",
    url: "https://www.myminifactory.com",
    tagline: "Forte em miniaturas e cultura geek.",
    description:
      "Especializado em miniaturas pra board games, RPG e cosplay. Modelos testados antes de publicar. Programa Tribes (assinatura pra criadores).",
    tier: "freemium",
    category: "marketplace",
    highlights: ["Miniaturas testadas", "Assinatura Tribes", "Comunidade RPG/board game"],
  },
  {
    slug: "stlbase",
    name: "STLBase",
    url: "https://stlbase.com",
    tagline: "Agregador europeu — busca cruzada.",
    description:
      "Busca em vários repositórios ao mesmo tempo. Útil quando você não sabe em qual site procurar.",
    tier: "free",
    category: "community",
    highlights: ["Multi-source", "Sem cadastro pra baixar", "Filtros avançados"],
  },
  {
    slug: "youmagine",
    name: "YouMagine",
    url: "https://www.youmagine.com",
    tagline: "Comunidade pequena, foco open source.",
    description:
      "Plataforma da UltiMaker (precursora do Thingiverse). Comunidade menor mas com modelos open source e licenças claras.",
    tier: "free",
    category: "community",
    ecosystem: "UltiMaker",
    highlights: ["Open source", "Sem ads", "Licenças explícitas"],
  },
  {
    slug: "cgtrader",
    name: "CGTrader",
    url: "https://www.cgtrader.com",
    tagline: "Profissional — paga, mas qualidade alta.",
    description:
      "Marketplace pago focado em 3D pra animação, jogos, AR/VR. Tem categoria 'Printable' com modelos otimizados.",
    tier: "paid",
    category: "marketplace",
    highlights: ["Qualidade profissional", "Comissão pro designer", "AR/VR também"],
  },
  {
    slug: "grabcad",
    name: "GrabCAD",
    url: "https://grabcad.com/library",
    tagline: "CAD engenharia — peças técnicas.",
    description:
      "Biblioteca de CAD de engenharia (parafusos, engrenagens, peças mecânicas). Excelente fonte pra reposição e modelos funcionais.",
    tier: "free",
    category: "engineering",
    highlights: ["Peças funcionais", "Formatos CAD (STEP, IGES)", "Comunidade de engenheiros"],
  },
  {
    slug: "free3d",
    name: "Free3D",
    url: "https://free3d.com",
    tagline: "Catálogo grande mas misturado.",
    description:
      "Grátis + pago, com muitos modelos pra render que precisam adaptação pra imprimir. Use com filtro de formato STL/OBJ.",
    tier: "freemium",
    category: "render",
    highlights: ["Catálogo grande", "Filtro por formato", "Mistura impressão + render"],
  },
  {
    slug: "sketchfab",
    name: "Sketchfab",
    url: "https://sketchfab.com",
    tagline: "Visualização 3D + downloads.",
    description:
      "Viewer 3D no browser, alguns modelos têm download grátis. Não foi feito pra impressão, mas dá pra achar coisas únicas (digitalizações de museus, scans 3D).",
    tier: "freemium",
    category: "render",
    highlights: ["Viewer 3D no navegador", "Scans de museus", "Algumas downloads grátis"],
  },
];

export const CATEGORY_LABEL: Record<SiteCategory, string> = {
  community: "Comunidade",
  marketplace: "Marketplace",
  engineering: "Engenharia / CAD",
  render: "Render / Visualização",
};

export const TIER_LABEL: Record<Tier, string> = {
  free: "Grátis",
  freemium: "Grátis + Pago",
  paid: "Pago",
};
