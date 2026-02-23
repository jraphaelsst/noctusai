export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "13.0.5"
  }
  public: {
    Tables: {
      atividades: {
        Row: {
          cliente_id: string
          created_at: string
          data_execucao: string
          descricao: string
          id: string
          tipo: Database["public"]["Enums"]["tipo_atividade"]
          usuario_id: string
        }
        Insert: {
          cliente_id: string
          created_at?: string
          data_execucao?: string
          descricao: string
          id?: string
          tipo?: Database["public"]["Enums"]["tipo_atividade"]
          usuario_id: string
        }
        Update: {
          cliente_id?: string
          created_at?: string
          data_execucao?: string
          descricao?: string
          id?: string
          tipo?: Database["public"]["Enums"]["tipo_atividade"]
          usuario_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "atividades_cliente_id_fkey"
            columns: ["cliente_id"]
            isOneToOne: false
            referencedRelation: "clientes"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "atividades_usuario_id_fkey"
            columns: ["usuario_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      clientes: {
        Row: {
          arquivado: boolean
          created_at: string
          email: string | null
          etapa_atual: Database["public"]["Enums"]["etapa_funil"]
          id: string
          interesse: string | null
          kanban_pos: number
          nome: string
          observacoes: string | null
          origem: string | null
          probabilidade: number
          telefone: string | null
          updated_at: string
          usuario_id: string
          valor_estimado: number
        }
        Insert: {
          arquivado?: boolean
          created_at?: string
          email?: string | null
          etapa_atual?: Database["public"]["Enums"]["etapa_funil"]
          id?: string
          interesse?: string | null
          kanban_pos?: number
          nome: string
          observacoes?: string | null
          origem?: string | null
          probabilidade?: number
          telefone?: string | null
          updated_at?: string
          usuario_id: string
          valor_estimado?: number
        }
        Update: {
          arquivado?: boolean
          created_at?: string
          email?: string | null
          etapa_atual?: Database["public"]["Enums"]["etapa_funil"]
          id?: string
          interesse?: string | null
          kanban_pos?: number
          nome?: string
          observacoes?: string | null
          origem?: string | null
          probabilidade?: number
          telefone?: string | null
          updated_at?: string
          usuario_id?: string
          valor_estimado?: number
        }
        Relationships: [
          {
            foreignKeyName: "clientes_usuario_id_fkey"
            columns: ["usuario_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      funil_movimentos: {
        Row: {
          cliente_id: string
          created_at: string
          de_etapa: Database["public"]["Enums"]["etapa_funil"] | null
          id: string
          motivo: string | null
          para_etapa: Database["public"]["Enums"]["etapa_funil"]
          responsavel_id: string
        }
        Insert: {
          cliente_id: string
          created_at?: string
          de_etapa?: Database["public"]["Enums"]["etapa_funil"] | null
          id?: string
          motivo?: string | null
          para_etapa: Database["public"]["Enums"]["etapa_funil"]
          responsavel_id: string
        }
        Update: {
          cliente_id?: string
          created_at?: string
          de_etapa?: Database["public"]["Enums"]["etapa_funil"] | null
          id?: string
          motivo?: string | null
          para_etapa?: Database["public"]["Enums"]["etapa_funil"]
          responsavel_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "funil_movimentos_cliente_id_fkey"
            columns: ["cliente_id"]
            isOneToOne: false
            referencedRelation: "clientes"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "funil_movimentos_responsavel_id_fkey"
            columns: ["responsavel_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      imoveis: {
        Row: {
          aceita_permutas: boolean
          andar: number | null
          ano_construcao: number | null
          area_privativa: number | null
          area_total: number | null
          bairro: string | null
          banheiros: number | null
          cep: string
          cidade: string | null
          complemento: string | null
          condominio: number | null
          condominio_nome: string | null
          created_at: string
          descricao_seo: string | null
          estado: string | null
          finalidade: Database["public"]["Enums"]["finalidade_imovel"]
          fotos: string[] | null
          id: string
          iptu: number | null
          latitude: number | null
          logradouro: string | null
          longitude: number | null
          lqs_score_hint: string | null
          numero: string | null
          observacoes_negociacao: string | null
          owner_id: string
          palavras_chave: string[] | null
          plantas: string[] | null
          pontos_de_interesse: string[] | null
          preco_pedido: number
          pronto_para_portais: boolean
          quartos: number | null
          status: string
          suites: number | null
          tipo: Database["public"]["Enums"]["tipo_imovel"]
          titulo_anuncio: string | null
          tour_virtual_url: string | null
          updated_at: string
          vagas: number | null
        }
        Insert: {
          aceita_permutas?: boolean
          andar?: number | null
          ano_construcao?: number | null
          area_privativa?: number | null
          area_total?: number | null
          bairro?: string | null
          banheiros?: number | null
          cep: string
          cidade?: string | null
          complemento?: string | null
          condominio?: number | null
          condominio_nome?: string | null
          created_at?: string
          descricao_seo?: string | null
          estado?: string | null
          finalidade?: Database["public"]["Enums"]["finalidade_imovel"]
          fotos?: string[] | null
          id?: string
          iptu?: number | null
          latitude?: number | null
          logradouro?: string | null
          longitude?: number | null
          lqs_score_hint?: string | null
          numero?: string | null
          observacoes_negociacao?: string | null
          owner_id: string
          palavras_chave?: string[] | null
          plantas?: string[] | null
          pontos_de_interesse?: string[] | null
          preco_pedido: number
          pronto_para_portais?: boolean
          quartos?: number | null
          status?: string
          suites?: number | null
          tipo: Database["public"]["Enums"]["tipo_imovel"]
          titulo_anuncio?: string | null
          tour_virtual_url?: string | null
          updated_at?: string
          vagas?: number | null
        }
        Update: {
          aceita_permutas?: boolean
          andar?: number | null
          ano_construcao?: number | null
          area_privativa?: number | null
          area_total?: number | null
          bairro?: string | null
          banheiros?: number | null
          cep?: string
          cidade?: string | null
          complemento?: string | null
          condominio?: number | null
          condominio_nome?: string | null
          created_at?: string
          descricao_seo?: string | null
          estado?: string | null
          finalidade?: Database["public"]["Enums"]["finalidade_imovel"]
          fotos?: string[] | null
          id?: string
          iptu?: number | null
          latitude?: number | null
          logradouro?: string | null
          longitude?: number | null
          lqs_score_hint?: string | null
          numero?: string | null
          observacoes_negociacao?: string | null
          owner_id?: string
          palavras_chave?: string[] | null
          plantas?: string[] | null
          pontos_de_interesse?: string[] | null
          preco_pedido?: number
          pronto_para_portais?: boolean
          quartos?: number | null
          status?: string
          suites?: number | null
          tipo?: Database["public"]["Enums"]["tipo_imovel"]
          titulo_anuncio?: string | null
          tour_virtual_url?: string | null
          updated_at?: string
          vagas?: number | null
        }
        Relationships: []
      }
      imoveis_perfis_permutas: {
        Row: {
          created_at: string
          id: string
          imovel_id: string
          perfil_permuta_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          imovel_id: string
          perfil_permuta_id: string
        }
        Update: {
          created_at?: string
          id?: string
          imovel_id?: string
          perfil_permuta_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "imoveis_perfis_permutas_imovel_id_fkey"
            columns: ["imovel_id"]
            isOneToOne: false
            referencedRelation: "imoveis"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "imoveis_perfis_permutas_perfil_permuta_id_fkey"
            columns: ["perfil_permuta_id"]
            isOneToOne: false
            referencedRelation: "perfis_permutas"
            referencedColumns: ["id"]
          },
        ]
      }
      metas: {
        Row: {
          carry_in: number
          carry_out: number
          categoria: Database["public"]["Enums"]["categoria_meta"]
          categoria_custom: string | null
          conclusao_prazo: Database["public"]["Enums"]["conclusao_prazo_meta"]
          created_at: string
          criada_manualmente: boolean
          data_prazo: string
          detalhes: string | null
          dias_restantes: number | null
          finalizada_em: string | null
          finalizada_no_prazo: boolean | null
          id: string
          meta_pretendida: number
          meta_realizada: number | null
          motivo_impedimento: string | null
          nivel_performance: Database["public"]["Enums"]["nivel_performance_meta"]
          nome: string | null
          status: Database["public"]["Enums"]["status_meta"]
          tem_impedimento: boolean
          tipo: Database["public"]["Enums"]["tipo_meta"]
          updated_at: string
          usuario_id: string
        }
        Insert: {
          carry_in?: number
          carry_out?: number
          categoria?: Database["public"]["Enums"]["categoria_meta"]
          categoria_custom?: string | null
          conclusao_prazo?: Database["public"]["Enums"]["conclusao_prazo_meta"]
          created_at?: string
          criada_manualmente?: boolean
          data_prazo: string
          detalhes?: string | null
          dias_restantes?: number | null
          finalizada_em?: string | null
          finalizada_no_prazo?: boolean | null
          id?: string
          meta_pretendida: number
          meta_realizada?: number | null
          motivo_impedimento?: string | null
          nivel_performance?: Database["public"]["Enums"]["nivel_performance_meta"]
          nome?: string | null
          status?: Database["public"]["Enums"]["status_meta"]
          tem_impedimento?: boolean
          tipo: Database["public"]["Enums"]["tipo_meta"]
          updated_at?: string
          usuario_id: string
        }
        Update: {
          carry_in?: number
          carry_out?: number
          categoria?: Database["public"]["Enums"]["categoria_meta"]
          categoria_custom?: string | null
          conclusao_prazo?: Database["public"]["Enums"]["conclusao_prazo_meta"]
          created_at?: string
          criada_manualmente?: boolean
          data_prazo?: string
          detalhes?: string | null
          dias_restantes?: number | null
          finalizada_em?: string | null
          finalizada_no_prazo?: boolean | null
          id?: string
          meta_pretendida?: number
          meta_realizada?: number | null
          motivo_impedimento?: string | null
          nivel_performance?: Database["public"]["Enums"]["nivel_performance_meta"]
          nome?: string | null
          status?: Database["public"]["Enums"]["status_meta"]
          tem_impedimento?: boolean
          tipo?: Database["public"]["Enums"]["tipo_meta"]
          updated_at?: string
          usuario_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "metas_corretor_id_fkey"
            columns: ["usuario_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      metas_config: {
        Row: {
          ativo: boolean
          categoria: Database["public"]["Enums"]["categoria_meta"]
          categoria_custom: string | null
          created_at: string
          id: string
          meta_pretendida: number
          tipo: Database["public"]["Enums"]["tipo_meta"]
          updated_at: string
          usuario_id: string
        }
        Insert: {
          ativo?: boolean
          categoria: Database["public"]["Enums"]["categoria_meta"]
          categoria_custom?: string | null
          created_at?: string
          id?: string
          meta_pretendida?: number
          tipo: Database["public"]["Enums"]["tipo_meta"]
          updated_at?: string
          usuario_id: string
        }
        Update: {
          ativo?: boolean
          categoria?: Database["public"]["Enums"]["categoria_meta"]
          categoria_custom?: string | null
          created_at?: string
          id?: string
          meta_pretendida?: number
          tipo?: Database["public"]["Enums"]["tipo_meta"]
          updated_at?: string
          usuario_id?: string
        }
        Relationships: []
      }
      negociacoes: {
        Row: {
          cliente_ofertante_id: string
          cliente_proprietario_id: string
          created_at: string
          id: string
          imovel_id: string
          observacoes: string | null
          owner_id: string
          perfil_permuta_id: string
          status_etapa: Database["public"]["Enums"]["status_negociacao"]
          timeline: Json | null
          updated_at: string
          valor_complemento: number | null
          valor_imovel: number
          valor_permuta: number
        }
        Insert: {
          cliente_ofertante_id: string
          cliente_proprietario_id: string
          created_at?: string
          id?: string
          imovel_id: string
          observacoes?: string | null
          owner_id: string
          perfil_permuta_id: string
          status_etapa?: Database["public"]["Enums"]["status_negociacao"]
          timeline?: Json | null
          updated_at?: string
          valor_complemento?: number | null
          valor_imovel: number
          valor_permuta: number
        }
        Update: {
          cliente_ofertante_id?: string
          cliente_proprietario_id?: string
          created_at?: string
          id?: string
          imovel_id?: string
          observacoes?: string | null
          owner_id?: string
          perfil_permuta_id?: string
          status_etapa?: Database["public"]["Enums"]["status_negociacao"]
          timeline?: Json | null
          updated_at?: string
          valor_complemento?: number | null
          valor_imovel?: number
          valor_permuta?: number
        }
        Relationships: [
          {
            foreignKeyName: "negociacoes_imovel_id_fkey"
            columns: ["imovel_id"]
            isOneToOne: false
            referencedRelation: "imoveis"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "negociacoes_perfil_permuta_id_fkey"
            columns: ["perfil_permuta_id"]
            isOneToOne: false
            referencedRelation: "perfis_permutas"
            referencedColumns: ["id"]
          },
        ]
      }
      password_request_codes: {
        Row: {
          admin_user_id: string
          code: string
          corretor_id: string
          created_at: string
          expires_at: string
          id: string
          temp_password: string
        }
        Insert: {
          admin_user_id: string
          code: string
          corretor_id: string
          created_at?: string
          expires_at: string
          id?: string
          temp_password: string
        }
        Update: {
          admin_user_id?: string
          code?: string
          corretor_id?: string
          created_at?: string
          expires_at?: string
          id?: string
          temp_password?: string
        }
        Relationships: []
      }
      perfis_permutas: {
        Row: {
          aceita_completar_diferenca: boolean
          ano_max: number | null
          ano_min: number | null
          categoria: Database["public"]["Enums"]["categoria_permuta"]
          cliente_ofertante_id: string
          created_at: string
          faixa_preco_max: number | null
          faixa_preco_min: number | null
          id: string
          limite_complemento: number | null
          marca: string | null
          metragem_max: number | null
          metragem_min: number | null
          modelo: string | null
          observacoes: string | null
          quartos_min: number | null
          quilometragem_max: number | null
          regiao_preferida: string[] | null
          status: string
          tipo_imovel: Database["public"]["Enums"]["tipo_imovel"] | null
          tipo_movel: Database["public"]["Enums"]["tipo_movel"] | null
          updated_at: string
          vagas_min: number | null
          valor_estimado: number | null
        }
        Insert: {
          aceita_completar_diferenca?: boolean
          ano_max?: number | null
          ano_min?: number | null
          categoria: Database["public"]["Enums"]["categoria_permuta"]
          cliente_ofertante_id: string
          created_at?: string
          faixa_preco_max?: number | null
          faixa_preco_min?: number | null
          id?: string
          limite_complemento?: number | null
          marca?: string | null
          metragem_max?: number | null
          metragem_min?: number | null
          modelo?: string | null
          observacoes?: string | null
          quartos_min?: number | null
          quilometragem_max?: number | null
          regiao_preferida?: string[] | null
          status?: string
          tipo_imovel?: Database["public"]["Enums"]["tipo_imovel"] | null
          tipo_movel?: Database["public"]["Enums"]["tipo_movel"] | null
          updated_at?: string
          vagas_min?: number | null
          valor_estimado?: number | null
        }
        Update: {
          aceita_completar_diferenca?: boolean
          ano_max?: number | null
          ano_min?: number | null
          categoria?: Database["public"]["Enums"]["categoria_permuta"]
          cliente_ofertante_id?: string
          created_at?: string
          faixa_preco_max?: number | null
          faixa_preco_min?: number | null
          id?: string
          limite_complemento?: number | null
          marca?: string | null
          metragem_max?: number | null
          metragem_min?: number | null
          modelo?: string | null
          observacoes?: string | null
          quartos_min?: number | null
          quilometragem_max?: number | null
          regiao_preferida?: string[] | null
          status?: string
          tipo_imovel?: Database["public"]["Enums"]["tipo_imovel"] | null
          tipo_movel?: Database["public"]["Enums"]["tipo_movel"] | null
          updated_at?: string
          vagas_min?: number | null
          valor_estimado?: number | null
        }
        Relationships: []
      }
      profiles: {
        Row: {
          avatar: string | null
          created_at: string
          email: string
          id: string
          last_activity_at: string | null
          nome: string
          telefone: string
          updated_at: string
        }
        Insert: {
          avatar?: string | null
          created_at?: string
          email: string
          id: string
          last_activity_at?: string | null
          nome: string
          telefone: string
          updated_at?: string
        }
        Update: {
          avatar?: string | null
          created_at?: string
          email?: string
          id?: string
          last_activity_at?: string | null
          nome?: string
          telefone?: string
          updated_at?: string
        }
        Relationships: []
      }
      status_pagina: {
        Row: {
          created_at: string
          id: string
          nome_pagina: string
          status: string
          tipo_pagina: string
          updated_at: string
        }
        Insert: {
          created_at?: string
          id?: string
          nome_pagina: string
          status?: string
          tipo_pagina?: string
          updated_at?: string
        }
        Update: {
          created_at?: string
          id?: string
          nome_pagina?: string
          status?: string
          tipo_pagina?: string
          updated_at?: string
        }
        Relationships: []
      }
      user_actions_log: {
        Row: {
          created_at: string
          descricao: string
          detalhes: Json | null
          entidade_id: string | null
          id: string
          tipo_acao: Database["public"]["Enums"]["tipo_acao"]
          tipo_entidade: Database["public"]["Enums"]["tipo_entidade"]
          usuario_id: string
        }
        Insert: {
          created_at?: string
          descricao: string
          detalhes?: Json | null
          entidade_id?: string | null
          id?: string
          tipo_acao: Database["public"]["Enums"]["tipo_acao"]
          tipo_entidade: Database["public"]["Enums"]["tipo_entidade"]
          usuario_id: string
        }
        Update: {
          created_at?: string
          descricao?: string
          detalhes?: Json | null
          entidade_id?: string | null
          id?: string
          tipo_acao?: Database["public"]["Enums"]["tipo_acao"]
          tipo_entidade?: Database["public"]["Enums"]["tipo_entidade"]
          usuario_id?: string
        }
        Relationships: []
      }
      user_roles: {
        Row: {
          created_at: string
          id: string
          role: Database["public"]["Enums"]["app_role"]
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          role: Database["public"]["Enums"]["app_role"]
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          role?: Database["public"]["Enums"]["app_role"]
          user_id?: string
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      atualizar_status_metas: { Args: never; Returns: Json }
      calcular_dias_restantes: {
        Args: { p_data_prazo: string }
        Returns: number
      }
      calcular_meta_proporcional: {
        Args: {
          p_data_ref: string
          p_meta_mensal: number
          p_tipo: Database["public"]["Enums"]["tipo_meta"]
        }
        Returns: number
      }
      calcular_nivel_performance: {
        Args: { p_meta_pretendida: number; p_meta_realizada: number }
        Returns: Database["public"]["Enums"]["nivel_performance_meta"]
      }
      concluir_meta_agrupada: { Args: { p_meta_id: string }; Returns: Json }
      current_date_sao_paulo: { Args: never; Returns: string }
      delete_expired_password_codes: { Args: never; Returns: undefined }
      desativar_metas_usuarios_inativos: { Args: never; Returns: Json }
      dias_uteis_mes: { Args: { p_data_ref: string }; Returns: number }
      dias_uteis_restantes_ano: {
        Args: { p_data_ref: string }
        Returns: number
      }
      dias_uteis_restantes_mes: {
        Args: { p_data_ref: string }
        Returns: number
      }
      dias_uteis_restantes_semana: {
        Args: { p_data_ref: string }
        Returns: number
      }
      dias_uteis_totais_ano: { Args: { p_data_ref: string }; Returns: number }
      dias_uteis_totais_mes: { Args: { p_data_ref: string }; Returns: number }
      dias_uteis_totais_semana: {
        Args: { p_data_ref: string }
        Returns: number
      }
      ensure_scaffold_meta: {
        Args: {
          p_categoria: Database["public"]["Enums"]["categoria_meta"]
          p_data_ref: string
          p_tipo: Database["public"]["Enums"]["tipo_meta"]
          p_usuario_id: string
        }
        Returns: string
      }
      generate_corretor_id: { Args: never; Returns: string }
      generate_imovel_id: { Args: never; Returns: string }
      generate_meta_id: { Args: never; Returns: string }
      generate_negociacao_id: { Args: never; Returns: string }
      generate_perfil_permuta_id: { Args: never; Returns: string }
      get_period_key: {
        Args: {
          data_ref: string
          tipo_meta: Database["public"]["Enums"]["tipo_meta"]
        }
        Returns: string
      }
      has_role: {
        Args: {
          _role: Database["public"]["Enums"]["app_role"]
          _user_id: string
        }
        Returns: boolean
      }
      normalize_timestamp_sp: { Args: { ts: string }; Returns: string }
      now_sao_paulo: { Args: never; Returns: string }
      period_end_date: {
        Args: {
          data_ref: string
          tipo_meta: Database["public"]["Enums"]["tipo_meta"]
        }
        Returns: string
      }
      rollup_metas: {
        Args: {
          p_categoria: Database["public"]["Enums"]["categoria_meta"]
          p_data_ref: string
          p_usuario_id: string
        }
        Returns: undefined
      }
      semanas_mes: { Args: { p_data_ref: string }; Returns: number }
    }
    Enums: {
      app_role: "admin" | "corretor" | "coordenador" | "dev"
      categoria_meta:
        | "captacao"
        | "visitas"
        | "contatos"
        | "propostas"
        | "fechamento"
        | "captacao_imoveis"
        | "captacao_compradores"
        | "atualizacao_imoveis"
        | "outro"
      categoria_permuta: "imovel" | "movel"
      conclusao_prazo_meta: "no_prazo" | "atrasada"
      etapa_funil:
        | "qualificacao"
        | "visitas"
        | "proposta"
        | "negociacao"
        | "fechado"
      finalidade_imovel: "venda" | "aluguel"
      nivel_performance_meta: "baixo" | "regular" | "bom" | "excelente"
      status_meta:
        | "aberta"
        | "concluida"
        | "atrasada"
        | "no_prazo"
        | "vence_amanha"
      status_negociacao:
        | "qualificacao"
        | "visitas"
        | "proposta"
        | "negociacao"
        | "fechado"
        | "cancelado"
      tipo_acao:
        | "criar"
        | "editar"
        | "excluir"
        | "concluir"
        | "arquivar"
        | "desarquivar"
        | "mover"
        | "login"
        | "logout"
      tipo_atividade:
        | "ligacao"
        | "email"
        | "reuniao"
        | "whatsapp"
        | "visita"
        | "proposta"
        | "negociacao"
        | "outro"
      tipo_entidade:
        | "meta"
        | "cliente"
        | "usuario"
        | "atividade"
        | "config_meta"
        | "auth"
        | "imovel"
        | "perfil_permuta"
        | "negociacao"
      tipo_imovel:
        | "casa"
        | "apartamento"
        | "terreno"
        | "comercial"
        | "rural"
        | "outro"
      tipo_meta: "diaria" | "semanal" | "mensal" | "anual"
      tipo_movel: "carro" | "moto"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {
      app_role: ["admin", "corretor", "coordenador", "dev"],
      categoria_meta: [
        "captacao",
        "visitas",
        "contatos",
        "propostas",
        "fechamento",
        "captacao_imoveis",
        "captacao_compradores",
        "atualizacao_imoveis",
        "outro",
      ],
      categoria_permuta: ["imovel", "movel"],
      conclusao_prazo_meta: ["no_prazo", "atrasada"],
      etapa_funil: [
        "qualificacao",
        "visitas",
        "proposta",
        "negociacao",
        "fechado",
      ],
      finalidade_imovel: ["venda", "aluguel"],
      nivel_performance_meta: ["baixo", "regular", "bom", "excelente"],
      status_meta: [
        "aberta",
        "concluida",
        "atrasada",
        "no_prazo",
        "vence_amanha",
      ],
      status_negociacao: [
        "qualificacao",
        "visitas",
        "proposta",
        "negociacao",
        "fechado",
        "cancelado",
      ],
      tipo_acao: [
        "criar",
        "editar",
        "excluir",
        "concluir",
        "arquivar",
        "desarquivar",
        "mover",
        "login",
        "logout",
      ],
      tipo_atividade: [
        "ligacao",
        "email",
        "reuniao",
        "whatsapp",
        "visita",
        "proposta",
        "negociacao",
        "outro",
      ],
      tipo_entidade: [
        "meta",
        "cliente",
        "usuario",
        "atividade",
        "config_meta",
        "auth",
        "imovel",
        "perfil_permuta",
        "negociacao",
      ],
      tipo_imovel: [
        "casa",
        "apartamento",
        "terreno",
        "comercial",
        "rural",
        "outro",
      ],
      tipo_meta: ["diaria", "semanal", "mensal", "anual"],
      tipo_movel: ["carro", "moto"],
    },
  },
} as const
