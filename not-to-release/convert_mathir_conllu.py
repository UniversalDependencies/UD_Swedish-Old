"""Post-correction of Conllu files converted from Mathir treebank.
Usage: python convert_mathir_conllu.py input_file.conllu output_file.conllu"""

import sys
import pyconll

def head_is_aux_candidate(token, sentence):
    """ Chacks if the head of a token is an auxiliary verb candidate,
    i.e. a verb with a lemma that is in the closed list of
    old Swedish auxiliary verbs."""
    head_id = token.head
    head_token = sentence[head_id]
    aux_lemmata = ['hava', 'magha', 'vilia', 'skula', 'þora', 'fa', 'kunna']
    return head_token.upos == 'VERB' and head_token.lemma in aux_lemmata

def handle_auxiliary(participle_id, sentence, message):
    """ Handles a detected auxiliary construction where the auxiliary 
    is the head of its participle dependent. Changes the auxiliary to AUX
    and makes the participle the head of the auxiliary."""
    participle_token = sentence[participle_id]
    aux_id = participle_token.head
    aux_token = sentence[aux_id] # Auxiliary verb
    # Make any dependent of the auxiliary dependent of the participle instead
    for token in sentence:
        if token.head == aux_id and token.id != participle_id:
            token.head = participle_id
    # Make head of auxiliary the head of participle
    head_id = aux_token.head
    participle_token.head = head_id
    # Give participle the deprel of auxiliary
    participle_token.deprel = aux_token.deprel
    # Make participle the head of the auxiliary 
    aux_token.head = participle_token.id
    # Change auxiliary's POS and deprel
    aux_token.upos = 'AUX'
    aux_token.deprel = 'aux'
    message += f"New auxiliary construction: {aux_token.form} ({aux_id}) {participle_token.form} ({participle_id})\n"
    return sentence, message

corpus = pyconll.load_from_file(sys.argv[1]) # load corpus
corpus_name = sys.argv[1].split('/')[-1].split('.')[0] # For naming new sent_id
new_sent_id = 1 # Sentence counter
possessive_prs = {"min", "þin", "sin", "hans", "hennar", "var", "iþar", "þera"}
numeral_lemmas = {"tver", "þrir", "fiurir", "fäm", "siäx", "siu", "atta", "nio", "tio", "tolf", "þrättan", "fiughurtan", "tiughu", "fiuratighi", "hundraþ", "þusand"}
log_message = ""
issue_message = ""

with open(sys.argv[2], 'w', encoding="utf-8") as outfile:
    for sentence in corpus:
        # Fix sentence metadata
        # Remove source text name
        sentence.remove_meta('source')
        # move sent_id to old_sent_id
        old_sent_id = sentence.meta_value('sent_id')
        sentence.set_meta('old_sent_id', old_sent_id)
        # set new UD-compliant sent-id
        sentence.set_meta('sent_id', f"swedish-old-{corpus_name}-{new_sent_id}")
        new_sent_id += 1
        sent_log_message = "" # Log message for changes made to the sentence
        sent_issue_message = "" # Potential issues that need to be fixed or checked manually

        for token in sentence:
            # Clear MISC field from 'ref' as it has no information
            token.misc = {'_':None}

            # Remove the feature "Variant" if present
            try: 
                del token.feats['Variant']
                #token.misc = {'Variant':{'Short'}}
            except KeyError:
                pass

            # Move feature "Reflex" to MISC field
            try:
                del token.feats['Reflex']
                token.misc = {'Reflex': {'Yes'}}
                sent_log_message += f"Moved Reflex feature to MISC column for {token.form}, {token.id}\n"
            except KeyError:
                pass
             
            # Change obl:arg (dative arguments) to obl for UD compliance
            if token.deprel == "obl:arg":
                token.deprel = "obl"
                sent_log_message += f"Changed obl:arg to obl for {token.form}, {token.id}\n"

################################## Handle verbs ########################################
            if token.upos == 'VERB':
                # Handle passive verbs
                try:
                    if token.feats['Voice'] == {'Mid'}:
                        # Change voice Middle to Passive for consistency with Swedish UD
                        token.feats['Voice'] = {'Pass'}

                        # Make sure the passive verb has a correctly labeled subject
                        # If there are multiple subjects, flag for manual checking
                        clausal_subects = [t for t in sentence if t.head == token.id and t.deprel == 'csubj']
                        pass_subjects = [t for t in sentence if t.head == token.id and t.deprel == 'nsubj']
                        if len(pass_subjects)+len(clausal_subects) > 1:
                            # Multiple subjects
                            sent_issue_message += f"Multiple subjects found for passive verb {token.form}, {token.id} in sentence {sentence.id}\n"
                        elif len(clausal_subects) == 1:
                            # There is a clausal subject
                            clausal_subj = clausal_subects[0]
                            clausal_subj.deprel = 'csubj:pass'
                            sent_log_message += f"Changed passive clausal subject with head {clausal_subj.form}, {clausal_subj.id} to csubj:pass\n"
                        elif len(pass_subjects) == 1:
                            # There is a nominal subject - change its deprel based on its case
                            subject = pass_subjects[0]
                            case = str(subject.feats["Case"])
                            if case == "{'Nom'}":
                                subject.deprel = 'nsubj:pass'
                                sent_log_message += f"Changed passive nominal subject to nsubj:pass: {subject.form}, {subject.id}\n"
                            # Change the dependency label of non-nominative subject
                            elif case == "{'Acc'}":
                                subject.deprel = 'obj'
                                sent_log_message += f"Changed passive accusative subject to obj: {subject.form}, {subject.id}\n"
                            else:
                                subject.deprel = 'obl:agent'
                                sent_log_message += f"Changed passive {case} subject with to obl:agent: {subject.form}, {subject.id}\n"
                except KeyError:
                    pass

                # Handle compound verb lemmas with "+" in them
                if '+' in token.lemma:
                    parts = token.lemma.split('+')
                    token.lemma = parts[0] # Change the verb lemma to be only the main verb
                    if token.lemma == "vara":
                        token.upos = "AUX" # Copula verb 'vara' should always be AUX
                    
                    # Find the particle token among the dependents
                    particles = [t for t in sentence if t.head == token.id and t.lemma == parts[1]]
                    if len(particles) == 0:
                        sent_issue_message += f"No particles {parts[1]} found for +-token {token.form}, {token.id} in sentence {sentence.id}\n"
                        pass
                    elif len(particles) > 1:
                        sent_issue_message += f"Multiple particles {parts[1]} found for +-token {token.form}, {token.id} in sentence {sentence.id}: {[token.id for token in particles]}\n"
                        pass
                    else:
                        particle_token = particles[0]
                        sent_log_message += f"Found +-compound: {token.lemma}+{particle_token.lemma}, {token.id}, particle is {particle_token.upos}, deprel {particle_token.deprel}\n"
                        
                        # If particle is ADP with deprel obl, change to compound:prt. Otherwise, leave relation as is.
                        if particle_token.upos == 'ADP' and particle_token.deprel == 'obl':
                            particle_token.deprel = 'compound:prt'
                            sent_log_message += f"Changed particle deprel to compound:prt: {particle_token.form}, {particle_token.id}, head: {token.form}\n"

                # Handle participles and infinitives
                try:
                    # Handle participles
                    if token.feats['VerbForm'] == {'Part'}:
                        if head_is_aux_candidate(token, sentence): # Check if participle is dependent of an auxiliary verb
                            # If so, treat as auxiliary construction
                            sentence, sent_log_message = handle_auxiliary(token.id, sentence, sent_log_message)
                        else: # Otherwise, treat as adjective
                            token.upos = 'ADJ'
                            if token.deprel == 'acl':
                                token.deprel = 'amod'
                            sent_log_message += f"Changed participle to adjective: {token.form}, {token.id}, deprel: {token.deprel}, head: {sentence[token.head].form}\n"
                    
                    # Also check infinitives for auxiliary constructions
                    elif token.feats['VerbForm'] == {'Inf'}:
                        # Check if infinitive has infinitive marker 'at' as dependent
                        has_at = any(t.lemma == 'at' for t in sentence if t.head == token.id)
                        if not has_at and head_is_aux_candidate(token, sentence):
                            # If the verb ha no infinitive marker and its head is an auxiliary candidate, treat as auxiliary construction
                            sentence, sent_log_message = handle_auxiliary(token.id, sentence, sent_log_message)
                except KeyError:
                    pass

############################ Handle pronouns and determiners ##############################
            elif token.upos == "PRON" or token.upos=="DET":
                # If no PronType, add PronType based on lemma (I added all I could find in the treebank)
                # All pronouns and determiners need to at least have a PronType or the UD validator will complain
                try:
                    token.feats["PronType"]
                except KeyError:
                    if token.lemma in {"baþir", "hvar", "alder"}:
                        token.feats["PronType"] = {"Tot"}
                    elif token.lemma == "þän": # Handle "þän"
                        # If it has deprel det, it's an article (the)
                        if token.deprel == "det":
                            token.feats["PronType"] = {"Art"}
                        else: # Otherwise, personal pronoun (it)
                            token.feats["PronType"] = {"Prs"}
                    elif token.lemma in {"en", "hin"}:
                        token.feats["PronType"] = {"Art"}
                    elif token.lemma in {"annar", "enka", "manger", "margher", "sumber", "nokor", "þyliker"}:
                        token.feats["PronType"] = {"Ind"}
                    elif token.lemma in {"ängin", "hvarghin"}:
                        token.feats["PronType"] = {"Neg"}
                    elif token.lemma in {"þänne", "sa"}:
                        token.feats["PronType"] = {"Dem"}
                    elif token.lemma in {"hvilikin", "hvad"}:
                        token.feats["PronType"] = {"Int"}
                    # Personal pronouns
                    elif token.lemma in {"han", "hon", "iak", "þu", "vi", "i", "þer"} or token.lemma in possessive_prs:
                        token.feats["PronType"] = {"Prs"}
                        token.upos = "PRON" # Ensure the UPOS is PRON and not DET

                    # Check if the token has PronType now
                    try: 
                        prontype = token.feats["PronType"]
                        sent_log_message += f"Added PronType {prontype} for token: {token.form}, {token.id}\n"
                    except KeyError:
                        # No PronType added
                        # Treat as numeral, as these are tagged as pronouns
                        token.upos = "NUM"
                        sent_log_message += f"Changed {token.form} ({token.id}) to numeral\n"
                        # Flag if there is a risk that this is actually a determiner/pronoun and not a numeral
                        if token.lemma not in numeral_lemmas and not token.lemma.isdigit():
                            sent_issue_message += f"Changed PRON/DET into NUM: {token.form} ({token.id}) in sentence {sentence.id}. If this is not a numeral, add lemma {token.lemma} to code.\n"
                        # Remove Number feature, not relevant to numerals
                        try:
                            del token.feats["Number"]
                        except KeyError:
                            pass
                        # Change deprel to 'nummod' if it is 'det', otherwise flag for manual checking
                        if token.deprel == "det":
                            token.deprel = "nummod"
                            sent_log_message += f"Changed relation from 'det' to 'nummod' for token {token.form} ({token.id}).\n"
                        else:
                            sent_issue_message += f"Deprel not changed for numeral. Please look over deprel for numeral: {token.form}, {token.id} in sentence {sentence.id}\n"

                # Mark possessive pronouns with deprel nmod:poss and Poss=Yes feature
                if token.form in possessive_prs or token.lemma in possessive_prs:
                    token.deprel = "nmod:poss"
                    token.feats["Poss"] = {"Yes"}
                    sent_log_message += f"Marked possessive pronoun: {token.form}, {token.id}, head: {sentence[token.head].form}\n"

########################### Handle nouns, proper nouns and pronouns ##############################
            if token.upos in {"NOUN", "PROPN", "PRON"}:
                # Change genitive nmod into nmod:poss
                try:
                    if token.feats["Case"] == {"Gen"} and token.deprel == "nmod":
                        # Only change if head is not also genitive
                        if sentence[token.head].feats["Case"] != {"Gen"}:
                            token.deprel = "nmod:poss"
                            sent_log_message += f"Changed genitive nmod into nmod:poss: {token.form}, {token.id}, head: {sentence[token.head].form}\n"
                        else: # If head is also genitive, we cannot be sure that there is a possesive relation
                            sent_issue_message += f"Skipped genitive nmod {token.form}, {token.id} because head {sentence[token.head].form} is also genitive. Check whether the word is possessive and should have ':poss' (sentence {sentence.id})\n"
                except KeyError: # Foreign nouns has no Case feature currently
                    pass

                # Specific fix for "herra abota" construction
                try: 
                    # If token is "härra" and the next token is "abbote"
                    if token.lemma == 'härra' and sentence[int(token.id)].lemma == 'abbote':
                        token.deprel = 'nmod' # Change deprel to nmod
                        token.head = str(int(token.id)+1) # Make "abbote" the head
                        sent_log_message += f"Fixed 'härra abbote' ({token.id}, {int(token.id)+1}) construction\n"
                except IndexError:
                    pass

############################ Handle other POS categories ##############################
            elif token.upos == "ADV":
                # Handle negations
                # Correct UPOS to PART and add Polarity feature
                if token.lemma in {"eighi", "eigh"}:
                    token.upos = "PART"
                    token.feats["Polarity"] = {"Neg"}
                    sent_log_message += f"Marked negation particle: {token.form}, {token.id}\n"
            
            elif token.upos == "SCONJ":
                # Attempt to handle relative clauses with 'sum' (consistently tagged as SCONJ in Mathir)
                if token.lemma == "sum":
                    try: # "sum" whose gradparent is nominal becomes relative pronoun
                        if sentence[sentence[token.head].head].upos in {"NOUN", "PROPN", "PRON"}:
                            token.upos = "PRON"
                            token.feats["PronType"] = {"Rel"}
                            # Change sum-clause to relative clause
                            sentence[token.head].deprel = "acl:relcl"
                            # If there is already a subject in the clause, make "sum" the object
                            if any(t.deprel in {"nsubj", "csubj"} for t in sentence if t.head == token.head):
                                token.deprel = "obj"
                            else: # Otherwise, make "sum" the subject
                                token.deprel = "nsubj"
                            sent_log_message += f"Changed 'sum' ({token.id}) to relative {token.deprel} pronoun.\n"
                        else:
                            sent_issue_message += f"Could not process 'sum', {token.id} in sentence {sentence.id}. Please check whether it should be relative pronoun or SCONJ.\n"
                    except KeyError:
                        sent_issue_message += f"Could not process 'sum', {token.id} in sentence {sentence.id}. Please check whether it should be relative pronoun or SCONJ.\n"

############################ Handle other issues not dependent on POS ##############################
            # Handle 'fixed' relations
            if token.deprel == "fixed":
                head = sentence[token.head]

                # Specific fix for "fyr än"
                if head.lemma == "fyr" and token.lemma == "än" and head.deprel != "fixed":
                    token.head = head.head
                    token.deprel = "mark"
                    token.upos = "SCONJ"
                    head.deprel = "mark"
                    head.upos = "ADV"
                    sent_log_message += f"Solved fixed SCONJ construction 'fyr än' (tokens {head.id} and {token.id})\n"
                
                # Specific fix for "þy at"
                elif head.lemma == "þy" and token.lemma == "at" and head.deprel != "fixed" and token.upos == "SCONJ":
                    # Change þy to pronoun and fix features
                    head.upos = "PRON"
                    head.feats["PronType"] = {"Dem"}
                    head.feats["Case"] = {"Dat"}
                    head.feats["Number"] = {"Sing"}
                    head.feats["Gender"] = {"Neut"}
                    # Change relations
                    at_clause_head = head.head # main verb of the following at-clause
                    prev_clause_head = sentence[at_clause_head].head # head of the overarching clause, often the previous
                    # Make þy an oblique argument in the previous clause head
                    head.head = prev_clause_head
                    head.deprel = "obl"
                    # Make 'at' a marker of the at-clause head
                    token.head = at_clause_head 
                    token.deprel = "mark"
                    # Make þy the head of the at-clause
                    sentence[at_clause_head].head = head.id
                    sentence[at_clause_head].deprel = "acl"
                    sent_log_message += f"Solved fixed SCONJ construction 'þy at' (tokens {head.id} and {token.id})\n"
                else:
                    # Add ExtPos to head that can easily be changed later
                    head.feats["ExtPos"] = {str(head.upos)}
                    sent_issue_message += f"Fixed construction found in {sentence.id} with POS {head.upos}: {head.lemma} ({head.id}), {token.lemma} ({token.id})\n"
            
            # Flag 'dislocated' relations
            elif token.deprel == "dislocated":
                head = sentence[token.head]
                sent_issue_message += f"Dislocated relation found in {sentence.id} between {head.form} ({head.id}) and {token.form} ({token.id})\n"
            
            # Flag foreign words
            if token.xpos == "F-":
                token.feats["Foreign"] = {"Yes"}
                sent_issue_message += f"Foreign word found in {sentence.id}: {token.form}, {token.id}\n"

            # Flag 'vara' that is not marked as copula
            if token.lemma == "vara" and token.deprel != "cop":
                sent_issue_message += f"'vara' with deprel {token.deprel}, {token.id} in sentence {sentence.id}, change to copula.\n"

        outfile.write(sentence.conll()) # Write the modified sentence to the output file
        outfile.write('\n\n')
        
        # Add log and issue messages for the sentence
        log_message += sentence.id + '\n'
        issue_message += sentence.id + '\n'
        if sent_log_message:
            log_message += sent_log_message + "\n"
        else:
            log_message += "No changes made.\n\n"
        if sent_issue_message:
            issue_message += sent_issue_message + "\n"
        else:
            issue_message += "No issues found.\n\n"

# Write log and issue messages into corpus-specific files in seoparate folders
with open(f"conversion_logfiles/conversion_log-{corpus_name}.txt", 'w', encoding="utf-8") as log_file:
    log_file.write(log_message)

with open(f"conversion_issues/conversion_issues-{corpus_name}.txt", 'w', encoding="utf-8") as issue_file:
    issue_file.write(issue_message)