import React, { createContext, useReducer, useContext, ReactNode } from 'react';
import { Prompt, getAdminPrompts, createPrompt, updatePrompt, deletePrompt, importPrompts } from '../api';

// State & Actions
interface State { prompts: Prompt[]; loading: boolean; error?: string }
type Action =
  | { type: 'LOAD_START' }
  | { type: 'LOAD_SUCCESS'; payload: Prompt[] }
  | { type: 'LOAD_FAIL'; payload: string }
  | { type: 'ADD'; payload: Prompt }
  | { type: 'UPDATE'; payload: Prompt }
  | { type: 'REMOVE'; payload: string };

const initialState: State = { prompts: [], loading: false };

const reducer = (s: State, a: Action): State => {
  switch(a.type) {
    case 'LOAD_START': return { ...s, loading: true, error: undefined };
    case 'LOAD_SUCCESS': return { prompts: a.payload, loading: false };
    case 'LOAD_FAIL': return { ...s, loading: false, error: a.payload };
    case 'ADD': return { ...s, prompts: [...s.prompts, a.payload] };
    case 'UPDATE':
      return {
        ...s,
        prompts: s.prompts.map(p => p.id === a.payload.id ? a.payload : p)
      };
    case 'REMOVE':
      return {
        ...s,
        prompts: s.prompts.filter(p => p.id !== a.payload)
      };
    default: return s;
  }
};

const AdminPromptContext = createContext<{
  state: State;
  loadPrompts: () => Promise<void>;
  addPrompt: (data: Omit<Prompt,'id'>) => Promise<void>;
  editPrompt: (id: string, data: Omit<Prompt,'id'>) => Promise<void>;
  removePrompt: (id: string) => Promise<void>;
  importFile: (file: File) => Promise<void>;
} | undefined>(undefined);

export const AdminPromptProvider = ({ children }: { children: ReactNode }) => {
  const [state, dispatch] = useReducer(reducer, initialState);

  const loadPrompts = async () => {
    dispatch({ type: 'LOAD_START' });
    try {
      const ps = await getAdminPrompts();
      dispatch({ type: 'LOAD_SUCCESS', payload: ps });
    } catch(e:any) {
      dispatch({ type: 'LOAD_FAIL', payload: e.message });
    }
  };

  const addPrompt = async (data: Omit<Prompt,'id'>) => {
    const p = await createPrompt(data);
    dispatch({ type: 'ADD', payload: p });
  };

  const editPrompt = async (id:string, data: Omit<Prompt,'id'>) => {
    const p = await updatePrompt(id, data);
    dispatch({ type: 'UPDATE', payload: p });
  };

  const removePrompt = async (id:string) => {
    await deletePrompt(id);
    dispatch({ type: 'REMOVE', payload: id });
  };

  const importFile = async (file: File) => {
    // hier ggf. FormData + api.importPrompts
    const { errors, created } = await importPrompts(file);
    for (const p of created) dispatch({ type: 'ADD', payload: p });
  };

  return (
    <AdminPromptContext.Provider value={{
      state, loadPrompts, addPrompt, editPrompt, removePrompt, importFile
    }}>
      {children}
    </AdminPromptContext.Provider>
  );
};

export const useAdminPrompt = () => {
  const ctx = useContext(AdminPromptContext);
  if (!ctx) throw new Error('useAdminPrompt must be inside AdminPromptProvider');
  return ctx;
};
