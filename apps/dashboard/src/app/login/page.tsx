import { supabaseBrowserAuthConfigured } from "@/lib/supabase/config";
import { LoginForm } from "./login-form";

export default function LoginPage() {
  // Browser Auth UI needs NEXT_PUBLIC_* keys; admin-token tab always available.
  return <LoginForm supabaseReady={supabaseBrowserAuthConfigured()} />;
}
