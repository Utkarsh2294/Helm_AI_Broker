import { create } from 'zustand';
// Authentication secrets stay in HttpOnly cookies. This store holds display state only.
export const useSessionStore = create(set => ({ user: null, setUser: user => set({ user }) }));
